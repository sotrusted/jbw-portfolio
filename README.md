# josephbochettowalsh.com

Django replacement for Joseph Bochetto Walsh's WordPress site, built on the
[`sotrusted/portfolio`](https://github.com/sotrusted/portfolio) artist-portfolio app.
Same look, same addresses, no WordPress: Joseph manages everything from `/admin/`.

## Run it locally

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py import_wordpress      # pulls all content from the live WordPress site
.venv/bin/python manage.py createsuperuser       # login for /admin/
.venv/bin/python manage.py runserver
```

`manage.py test` runs the test suite.

## How the site is organised

| Old WordPress thing | Here |
| --- | --- |
| Menu sections (Paintings, Drawings, Photography…) | top-level **Categories** (`/category/paintings/`) |
| Series (pelagic, jellies, beasts…) | **Categories** with a parent (`/pelagic/`) |
| Mixed Media, Surface Design | top-level categories with no series, so they open straight to a gallery |
| Cover images on a section page | **Series tiles**, edited inline on the series' category page. A series can have several |
| Portfolio items | **Artworks** (`/portfolio/flight/`) with medium, dimensions, price |
| "Home Page" category | the **featured** checkbox on an artwork (home page slideshow) |
| "view on wall" | per-artwork setting: which wall photo, plus size and position on it |
| Information page | the single **Information page** record |

Artworks are drag-sortable in the admin list; galleries show them top to bottom in that order.
Uploading an image automatically produces the 1800px display copy and 800px thumbnail.

Old addresses keep working: duplicate WordPress series posts (`/pelagic-2/`, `/garden-3/`…),
`/welcome/` and `/artists-statement/` permanently redirect to their new homes.

## Importing from WordPress

`import_wordpress` reads the WordPress REST API, reads each item page for the details the API
doesn't expose (medium / size / price / view-on-wall placement), and downloads the images.
Everything is cached in `wp_export/`, so it is safe to stop and re-run; existing artworks are
updated by slug, never duplicated. Run it with `--refresh-api` just before switching the domain
over to pick up anything Joseph changed in the meantime.

Known gaps in the source data: six portfolio items have no image on WordPress and are skipped
(`yellow-totem`, `gold-totem`, `red-nest`, `pale-nest`, `green-nest`, `dune-7`), and ~24 items
belong to no category there, so they are imported without one (reachable by address, not shown
in any gallery).

## The admin, for Joseph

`/admin/` is the whole product from Joseph's side, so it is built for him rather than for a
developer: plain-language labels and help text, large type and 44px touch targets, previews of
every picture, and a layout that works on a phone or tablet.

- **Dashboard** — big labelled shortcuts for the six things he actually does.
- **Add several at once** — upload a batch of pictures; each becomes an artwork named after its
  file, with a shared gallery, materials and price. Details can be corrected afterwards.
- **"View on wall"** — drag the work around a photo of a room and drag its corner to resize.
  The percentages underneath are written for him; he never types a number.
- **Reordering** — drag the grip in the artworks list. Filter by gallery first: every gallery
  fits on one page, so a whole series can be reordered without paging.
- **Newly added works** go to the top of their gallery automatically.
- **Information page** skips the list and opens straight into the form, since there is only one.

## Media (S3)

Uploaded images live in the public-read bucket `jbw-media-<aws account>`; pages link to it
directly. Set `AWS_STORAGE_BUCKET_NAME` to switch it on (without it, files go to `media/`, which
is what local development uses). `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are only needed
where someone uploads through the admin.

```sh
.venv/bin/python deploy/aws_setup.py                     # one-time: bucket, scoped IAM user, .env
set -a; . ./.env; set +a
.venv/bin/python manage.py upload_media_to_s3            # push local media/ to the bucket (re-runnable)
```

## Content fixture

`artworks/fixtures/content.json` is a snapshot of every category, artwork, tile and the
information page, so a new deployment has the full site without re-running the WordPress import:
`python manage.py loaddata content`. Refresh it with
`python manage.py dumpdata artworks --indent 1 -o artworks/fixtures/content.json`.

## Deploying

Environment variables (see `.env.example`):

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | a long random string |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_ALLOWED_HOSTS` | `josephbochettowalsh.com,www.josephbochettowalsh.com` |
| `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME` | the media bucket |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | the `jbw-vm-s3` user's key |

### Production server (nginx + gunicorn + systemd)

Lives in `~/jbw-portfolio` on the server, the same way the other sites there are set up.

```sh
git clone <this repo> ~/jbw-portfolio && cd ~/jbw-portfolio
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in, chmod 600
set -a; . ./.env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata content     # first install only - it overwrites admin edits
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
sudo bash deploy/install.sh     # systemd unit + nginx site; reloads nginx only if `nginx -t` passes
```

Updating: `git push prod main`, then `ssh 23.94.179.21 'bash ~/jbw-portfolio/deploy/update.sh'`.

That script does a full restart rather than a SIGHUP reload on purpose: gunicorn reloads code on
SIGHUP but keeps the environment it started with, so edits to `.env` would otherwise be ignored
while appearing to have worked.

After DNS points at the server: `sudo certbot --nginx -d josephbochettowalsh.com -d www.josephbochettowalsh.com`.

### Render (preview)

`render.yaml` is a Blueprint for a free web service. Its filesystem is throwaway, so `build.sh`
rebuilds the database from the content fixture on every deploy: fine for showing the site,
not for editing it. Set `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` in the Render
dashboard if you want an admin login on the preview.
