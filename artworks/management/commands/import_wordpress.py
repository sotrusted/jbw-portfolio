"""Import the old WordPress site (josephbochettowalsh.com) into this project.

    python manage.py import_wordpress            # everything
    python manage.py import_wordpress --limit 20 # quick trial run

Everything fetched is cached under wp_export/, so re-running is cheap and never re-downloads.
Delete that folder (or pass --refresh-api) to pick up changes made on the WordPress site.
Re-running updates existing artworks by slug rather than duplicating them.
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware

from artworks.models import Artwork, Bio, Category, SeriesTile

SITE = 'https://josephbochettowalsh.com'
# The host's mod_security rejects requests that don't look like a browser.
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/html;q=0.9, */*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}
DELAY = 0.5  # seconds between requests to the live site

SECTION_ORDER = ['paintings', 'drawings', 'mixed-media', 'photography', 'surface-design']
SECTION_LAYOUT = {'mixed-media': Category.LAYOUT_MASONRY}
HOME_CATEGORY = 'home-page'
# WordPress series posts are matched to portfolio categories by name; these differ.
CATEGORY_NAME_TO_POST_TITLE = {'detail': 'details'}
WALL_PHOTOS = {
    'wall-small.jpg': f'{SITE}/wp-content/uploads/2020/07/VOW-small.jpg',
    'wall-large.jpg': f'{SITE}/wp-content/uploads/2020/07/VOW-landscape.jpg',
}

DIMENSIONS = re.compile(r'\d\s*(?:"|”|″|\'\'|in\.?)?\s*[x×]\s*\d', re.I)
PRICE = re.compile(r'[$€£]|\bsold\b|\bnfs\b|not for sale|\bcontact\b|\binquire\b', re.I)


class Command(BaseCommand):
    help = 'Import categories, artworks, series tiles and the information page from the old WordPress site.'

    def add_arguments(self, parser):
        parser.add_argument('--cache-dir', default=str(settings.BASE_DIR / 'wp_export'))
        parser.add_argument('--limit', type=int, help='Only import the first N artworks (for a trial run).')
        parser.add_argument('--refresh-api', action='store_true', help='Re-fetch the WordPress listings.')

    def handle(self, *args, **options):
        self.cache = Path(options['cache_dir'])
        self.refresh_api = options['refresh_api']
        self.fetched = 0

        wp_categories = {c['id']: c for c in self.api('portfolio_category')}
        items = self.api('portfolio', fields='id,slug,title,date,link,featured_media,portfolio_category,menu_order')
        media = {m['id']: m for m in self.api('media', fields='id,source_url')}
        posts = self.api('posts', fields='id,slug,title,date,featured_media')
        pages = {p['slug']: p for p in self.api('pages', fields='id,slug,content')}

        categories = self.import_categories(wp_categories, items, media, posts)
        self.import_tiles(posts, wp_categories, categories, media)
        self.import_artworks(items, wp_categories, categories, media, options['limit'])
        self.import_information(pages.get('information'))
        self.import_wall_photos()
        self.stdout.write(self.style.SUCCESS(
            f'Done: {Category.objects.count()} categories, {Artwork.objects.count()} artworks, '
            f'{SeriesTile.objects.count()} tiles ({self.fetched} requests to the live site).'))

    # -- fetching ----------------------------------------------------------------------------

    def fetch(self, url):
        request = urllib.request.Request(url, headers=HEADERS)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    self.fetched += 1
                    time.sleep(DELAY)
                    return response.read(), response.headers
            except urllib.error.HTTPError as error:
                if error.code < 500:
                    raise
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f'Giving up on {url}')

    def api(self, endpoint, fields=None):
        path = self.cache / 'api' / f'{endpoint}.json'
        if path.exists() and not self.refresh_api:
            return json.loads(path.read_text())
        rows, page = [], 1
        while True:
            query = {'per_page': 100, 'page': page}
            if fields:
                query['_fields'] = fields
            body, headers = self.fetch(f'{SITE}/wp-json/wp/v2/{endpoint}?{urllib.parse.urlencode(query)}')
            rows += json.loads(body)
            if page >= int(headers.get('X-WP-TotalPages', 1)):
                break
            page += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))
        self.stdout.write(f'  fetched {len(rows)} {endpoint}')
        return rows

    def item_page(self, item):
        path = self.cache / 'items' / f"{item['slug']}.html"
        if not path.exists():
            body, _ = self.fetch(item['link'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        return path.read_text(encoding='utf-8', errors='replace')

    def download(self, url):
        """Return the local cached path for an uploaded file, downloading it on first use."""
        relative = urllib.parse.urlparse(url).path.split('/wp-content/uploads/', 1)[-1]
        path = self.cache / 'uploads' / urllib.parse.unquote(relative)
        if not path.exists():
            body, _ = self.fetch(urllib.parse.quote(url, safe=':/%'))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        return path

    # -- importing ---------------------------------------------------------------------------

    def import_categories(self, wp_categories, items, media, posts):
        """Create sections and series. Returns {wordpress category id: Category}."""
        importable = [i for i in items if i['featured_media'] in media]
        used = {cid for i in importable for cid in i['portfolio_category']}
        post_slugs = {}
        for post in posts:
            title = html.unescape(post['title']['rendered']).strip().lower()
            post_slugs.setdefault(title, set()).add(re.sub(r'-\d+$', '', post['slug']))

        result = {}
        for order, slug in enumerate(SECTION_ORDER):
            wp = next(c for c in wp_categories.values() if c['slug'] == slug and not c['parent'])
            result[wp['id']], _ = Category.objects.update_or_create(slug=slug, defaults={
                'name': self.section_name(wp['name']), 'parent': None, 'order': order,
                'layout': SECTION_LAYOUT.get(slug, Category.LAYOUT_TILES),
            })
        series = [c for c in wp_categories.values() if c['parent'] in result and c['id'] in used]
        for order, wp in enumerate(sorted(series, key=lambda c: c['name'].lower())):
            name = html.unescape(wp['name'])
            title = CATEGORY_NAME_TO_POST_TITLE.get(name.lower(), name.lower())
            # the gallery keeps the address of its WordPress post, e.g. /details/ for category "detail"
            slug = min(post_slugs.get(title, {wp['slug']}), key=len)
            result[wp['id']], _ = Category.objects.update_or_create(slug=slug, defaults={
                'name': title if title != name.lower() else name, 'parent': result[wp['parent']], 'order': order,
            })
        skipped = [c['name'] for c in wp_categories.values()
                   if c['id'] not in result and c['slug'] != HOME_CATEGORY]
        if skipped:
            self.stdout.write(f"  categories with no importable works, skipped: {', '.join(skipped)}")
        return result

    @staticmethod
    def section_name(name):
        name = html.unescape(name)
        return name.title() if name.islower() else name  # "drawings" sits beside "Paintings" in the menu

    def import_tiles(self, posts, wp_categories, categories, media):
        by_title = {}
        for wp_id, category in categories.items():
            if category.parent_id:
                by_title[category.name.lower()] = category
        for tile in SeriesTile.objects.all():  # rebuilt from scratch; take the old files with them
            tile.image.delete(save=False)
            tile.image_thumb.delete(save=False)
            tile.delete()
        newest_first = sorted(posts, key=lambda p: p['date'], reverse=True)
        for order, post in enumerate(newest_first):
            category = by_title.get(html.unescape(post['title']['rendered']).strip().lower())
            source = media.get(post['featured_media'])
            if not category or not source:
                self.stdout.write(f"  tile skipped: {post['slug']}")
                continue
            local = self.download(source['source_url'])
            tile = SeriesTile(category=category, order=order)
            with local.open('rb') as handle:
                tile.image.save(local.name, File(handle), save=True)

    def import_artworks(self, items, wp_categories, categories, media, limit):
        home_id = next((c['id'] for c in wp_categories.values() if c['slug'] == HOME_CATEGORY), None)
        # Galleries showed newest first unless a manual menu_order said otherwise; Artwork sorts by -order.
        ranked = sorted(items, key=lambda i: (-i['menu_order'], i['date']))
        rank = {item['id']: position for position, item in enumerate(ranked, start=1)}
        todo = [i for i in items if i['featured_media'] in media]
        no_image = [i['slug'] for i in items if i['featured_media'] not in media]
        if no_image:
            self.stdout.write(f"  no image on WordPress, skipped: {', '.join(no_image)}")
        if limit:
            featured_first = sorted(todo, key=lambda i: home_id not in i['portfolio_category'])
            todo = featured_first[:limit]

        for count, item in enumerate(todo, start=1):
            detail = self.parse_item_page(self.item_page(item))
            wp_ids = [cid for cid in item['portfolio_category'] if cid in categories]
            # prefer the series over its parent section when a work is filed under both
            wp_ids.sort(key=lambda cid: categories[cid].parent_id is None)
            fields = {
                'title': detail['title'] or html.unescape(item['title']['rendered']),
                'category': categories[wp_ids[0]] if wp_ids else None,
                'is_featured': home_id in item['portfolio_category'],
                'order': rank[item['id']],
                **detail['fields'],
            }
            artwork = Artwork.objects.filter(slug=item['slug']).first() or Artwork(slug=item['slug'])
            for name, value in fields.items():
                setattr(artwork, name, value)
            local = self.download(media[item['featured_media']]['source_url'])
            if artwork.image and Path(artwork.image.name).stem.startswith(local.stem[:40]):
                artwork.save()
            else:
                with local.open('rb') as handle:
                    artwork.image.save(local.name, File(handle), save=True)
            created = parse_datetime(item['date'])
            Artwork.objects.filter(pk=artwork.pk).update(created_at=make_aware(created) if created.tzinfo is None else created)
            if count % 25 == 0:
                self.stdout.write(f'  {count}/{len(todo)} artworks')

    def parse_item_page(self, page):
        """Medium / size / price and the view-on-wall placement only exist in the rendered page."""
        title = re.search(r'<h2 class="info-title">(.*?)</h2>', page, re.S)
        fields = {'medium': '', 'dimensions': '', 'price': '', 'wall_view': Artwork.WALL_NONE}
        description = re.search(r'<h3 class="info-description">(.*?)</h3>', page, re.S)
        lines = re.split(r'<br\s*/?>', description.group(1)) if description else []
        for line in (html.unescape(re.sub(r'<[^>]+>', '', l)).strip() for l in lines):
            if not line:
                continue
            if DIMENSIONS.search(line) and not fields['dimensions']:
                fields['dimensions'] = line
            elif PRICE.search(line) and not fields['price']:
                fields['price'] = line
            elif not fields['medium']:
                fields['medium'] = line
            else:
                fields['medium'] += f', {line}'

        # the link is left in the markup, commented out, when the feature is off for a work
        live = re.sub(r'<!--.*?-->', '', page, flags=re.S)
        wall = re.search(r'class="hentry VOW-(Small|Large)">\s*<div class="vow" style="([^"]*)"', page)
        if wall and 'vow-link' in live:
            fields['wall_view'] = Artwork.WALL_SMALL if wall.group(1) == 'Small' else Artwork.WALL_LARGE
            style = dict(re.findall(r'([a-z-]+)\s*:\s*([\d.]+)', wall.group(2)))
            # the old mockup was a fixed 1000 x 750 box; CSS padding percentages are relative to its width
            fields['wall_width'] = round(float(style.get('width', 240)) / 10, 2)
            fields['wall_left'] = float(style.get('padding-left', 32))
            fields['wall_top'] = round(float(style.get('padding-top', 20)) * 1000 / 750, 2)
        return {'title': html.unescape(title.group(1).strip()) if title else '', 'fields': fields}

    def import_information(self, page):
        if not page:
            return
        content = page['content']['rendered']

        def text(fragment):
            return html.unescape(re.sub(r'<[^>]+>', '', fragment)).replace('\xa0', ' ').strip()

        justified = [text(p) for p in re.findall(r'<p class="justify[^"]*">(.*?)</p>', content, re.S)]
        exhibitions = re.search(r'EXHIBITIONS</h2>.*?<p[^>]*>(.*?)</p>', content, re.S)
        email = re.search(r'mailto:([^"]+)"', content)
        instagram = re.search(r'instagram:\s*([\w.]+)', text(content), re.I)
        bio = Bio.objects.first() or Bio()
        bio.statement = justified[0] if justified else ''
        bio.content = '\n\n'.join(justified[1:])
        bio.exhibitions = '\n'.join(text(line) for line in re.split(r'<br\s*/?>', exhibitions.group(1))) if exhibitions else ''
        bio.email = email.group(1) if email else ''
        bio.instagram = instagram.group(1) if instagram else ''
        bio.save()
        image_fields = ['statement_image', 'statement_banner', 'biography_image', 'biography_banner']
        for field, url in zip(image_fields, re.findall(r'<img[^>]+src="([^"]+)"', content)):
            if getattr(bio, field):
                continue
            local = self.download(url)
            with local.open('rb') as handle:
                getattr(bio, field).save(local.name, File(handle), save=False)
        bio.save()

    def import_wall_photos(self):
        static_dir = Path(__file__).resolve().parents[2] / 'static' / 'artworks'
        for name, url in WALL_PHOTOS.items():
            target = static_dir / name
            if not target.exists():
                target.write_bytes(self.download(url).read_bytes())
