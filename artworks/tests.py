import shutil
import tempfile
from unittest.mock import patch
from io import BytesIO

from django.contrib.admin import helpers
from django.core import mail
from django.core.cache import cache
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .management.commands.import_wordpress import Command
from .models import Artwork, Bio, Category, ContactMessage, SeriesTile

MEDIA_ROOT = tempfile.mkdtemp()


def upload(name='work.png', size=(1200, 900)):
    buffer = BytesIO()
    Image.new('RGB', size, (120, 140, 160)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class SiteTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.paintings = Category.objects.create(name='Paintings', slug='paintings', order=0)
        self.pelagic = Category.objects.create(name='pelagic', slug='pelagic', parent=self.paintings)
        self.surface = Category.objects.create(name='Surface Design', slug='surface-design', order=1)
        SeriesTile.objects.create(category=self.pelagic, image=upload('tile.png'))
        self.works = [
            Artwork.objects.create(title=f'pelagic {n}', slug=f'pelagic-{n}', image=upload(), category=self.pelagic,
                                   order=n, medium='oil on paper', dimensions='22" x 30"', price='$900')
            for n in (1, 2, 3)
        ]

    def test_renditions_and_dimensions_are_built_on_save(self):
        work = self.works[0]
        self.assertEqual((work.width, work.height), (1200, 900))
        self.assertTrue(work.image_thumb.name.endswith('.jpg'))
        with Image.open(work.image_thumb.path) as thumb:
            self.assertEqual(max(thumb.size), 800)

    def test_pages_render(self):
        Artwork.objects.filter(pk=self.works[0].pk).update(is_featured=True)
        for url in ('/', '/category/paintings/', '/pelagic/', '/surface-design/', '/information/',
                    '/portfolio/pelagic-2/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_section_links_tiles_to_their_series(self):
        response = self.client.get('/category/paintings/')
        self.assertContains(response, 'href="/pelagic/"')

    def test_gallery_shows_highest_order_first(self):
        response = self.client.get('/pelagic/')
        self.assertEqual([w.slug for w in response.context['page']], ['pelagic-3', 'pelagic-2', 'pelagic-1'])

    def test_detail_shows_info_and_neighbours(self):
        response = self.client.get('/portfolio/pelagic-2/')
        self.assertContains(response, 'oil on paper')
        self.assertContains(response, '$900')
        self.assertEqual(response.context['prev_artwork'], 'pelagic-3')
        self.assertEqual(response.context['next_artwork'], 'pelagic-1')

    def test_view_on_wall_is_offered_by_default_and_can_be_turned_off(self):
        self.assertContains(self.client.get('/portfolio/pelagic-2/'), 'view on wall')
        Artwork.objects.filter(slug='pelagic-2').update(wall_view=Artwork.WALL_NONE)
        self.assertNotContains(self.client.get('/portfolio/pelagic-2/'), 'view on wall')

    def test_old_wordpress_addresses_redirect(self):
        for old, new in (('/pelagic-3/', '/pelagic/'), ('/paintings/', '/category/paintings/'),
                         ('/category/surface-design/', '/surface-design/'), ('/welcome/', '/'),
                         ('/artists-statement/', '/information/#artist')):
            with self.subTest(old=old):
                self.assertRedirects(self.client.get(old), new, status_code=301, fetch_redirect_response=False)

    def test_unknown_address_is_404(self):
        self.assertEqual(self.client.get('/nothing-here/').status_code, 404)
        self.assertEqual(self.client.get('/nothing-9/').status_code, 404)

    def test_htmx_request_gets_only_the_items(self):
        response = self.client.get(reverse('gallery', args=['pelagic']), headers={'HX-Request': 'true'})
        self.assertNotContains(response, '<html')
        self.assertContains(response, 'pelagic 1')


class ItemPageParsingTests(TestCase):
    PAGE = '''
      <div id="info-box"> <h2 class="info-title">flight</h2>
      <h3 class="info-description">ink, pigment, oil on cardboard<br> 13" x 16"<br> $750</h3>
      <h5>{link}</h5></div>
      <div id="fancyboxID-1" class="hentry VOW-Large">
        <div class="vow" style="width:128px; padding-top:22%; padding-left:42%"><img src="x.jpg"></div></div>
    '''
    LINK = '<a href="#fancyboxID-1" class="fancybox-inline vow-link">view on wall</a>'

    def test_fields_and_wall_placement(self):
        parsed = Command().parse_item_page(self.PAGE.format(link=self.LINK))
        self.assertEqual(parsed['title'], 'flight')
        self.assertEqual(parsed['fields'], {
            'medium': 'ink, pigment, oil on cardboard', 'dimensions': '13" x 16"', 'price': '$750',
            'wall_view': 'large', 'wall_width': 12.8, 'wall_left': 42.0, 'wall_top': 29.33,
        })

    def test_commented_out_wall_link_means_disabled(self):
        parsed = Command().parse_item_page(self.PAGE.format(link=f'<!--{self.LINK}-->'))
        self.assertEqual(parsed['fields']['wall_view'], '')

    def test_licensing_note_lands_in_price(self):
        page = '<h2 class="info-title">morning 3</h2><h3 class="info-description">contact for licensing and print<br> <br> </h3>'
        fields = Command().parse_item_page(page)['fields']
        self.assertEqual((fields['medium'], fields['price']), ('', 'contact for licensing and print'))


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AdminTests(TestCase):
    """The admin is the product for Joseph, so its pages are covered like any other."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_superuser('joseph', 'j@example.com', 'pw-for-tests-only')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(self.user)
        self.section = Category.objects.create(name='Paintings', slug='paintings')
        self.series = Category.objects.create(name='pelagic', slug='pelagic', parent=self.section)
        self.artwork = Artwork.objects.create(title='red pelagic', slug='red-pelagic', image=upload(),
                                              category=self.series, wall_view=Artwork.WALL_LARGE)

    def test_dashboard_offers_the_main_tasks(self):
        response = self.client.get('/admin/')
        for label in ('Add an artwork', 'Add several at once', 'Front page pictures',
                      'Galleries &amp; menu', 'Information page'):
            self.assertContains(response, label)

    def test_change_page_has_preview_and_wall_picker(self):
        response = self.client.get(f'/admin/artworks/artwork/{self.artwork.pk}/change/')
        self.assertContains(response, 'big-preview')
        self.assertContains(response, 'wall-picker')
        self.assertContains(response, 'artworks/wall-picker.js')
        self.assertContains(response, 'artworks/admin.css')

    def test_add_page_hides_preview_and_picker_until_there_is_a_picture(self):
        response = self.client.get('/admin/artworks/artwork/add/')
        self.assertNotContains(response, 'big-preview')
        self.assertNotContains(response, 'wall-stage')
        self.assertNotContains(response, 'Picture now')
        # the room is still offered, and defaults to the wide room
        self.assertContains(response, 'id_wall_view')
        self.assertEqual(response.context['adminform'].form['wall_view'].initial, Artwork.WALL_LARGE)

    def test_new_artworks_offer_view_on_wall_by_default(self):
        self.assertEqual(Artwork().wall_view, Artwork.WALL_LARGE)

    def test_move_selected_artworks_to_another_gallery(self):
        other = Category.objects.create(name='garden', slug='garden', parent=self.section)
        post = {'action': 'move_to_gallery', helpers.ACTION_CHECKBOX_NAME: [self.artwork.pk]}
        confirm = self.client.post('/admin/artworks/artwork/', post)
        self.assertContains(confirm, 'Move to another gallery')
        self.client.post('/admin/artworks/artwork/', {**post, 'apply': '1', 'category': other.pk}, follow=True)
        self.artwork.refresh_from_db()
        self.assertEqual(self.artwork.category, other)

    def test_front_page_actions(self):
        post = {helpers.ACTION_CHECKBOX_NAME: [self.artwork.pk]}
        self.client.post('/admin/artworks/artwork/', {**post, 'action': 'show_on_front_page'}, follow=True)
        self.assertTrue(Artwork.objects.get(pk=self.artwork.pk).is_featured)
        self.client.post('/admin/artworks/artwork/', {**post, 'action': 'remove_from_front_page'}, follow=True)
        self.assertFalse(Artwork.objects.get(pk=self.artwork.pk).is_featured)

    def test_metadata_is_editable_straight_from_the_list(self):
        response = self.client.get('/admin/artworks/artwork/')
        self.assertContains(response, 'name="form-0-price"')
        self.assertContains(response, 'name="form-0-dimensions"')
        self.assertContains(response, 'name="form-0-medium"')

    def test_bulk_upload_creates_one_artwork_per_file(self):
        response = self.client.post('/admin/artworks/artwork/bulk-upload/', {
            'images': [upload('red-garden-4.png'), upload('blue_garden_2.png')],
            'category': self.series.pk, 'medium': 'oil on paper', 'price': '$400',
        }, follow=True)
        self.assertContains(response, 'Added 2 artworks')
        added = Artwork.objects.filter(medium='oil on paper')
        self.assertEqual(sorted(added.values_list('title', flat=True)), ['blue garden 2', 'red garden 4'])
        self.assertTrue(all(a.image_thumb and a.category == self.series for a in added))

    def test_bulk_upload_without_files_is_rejected(self):
        response = self.client.post('/admin/artworks/artwork/bulk-upload/', {'category': self.series.pk})
        self.assertEqual(Artwork.objects.count(), 1)
        self.assertContains(response, 'field is required')

    def test_new_artwork_goes_to_the_top_of_its_gallery(self):
        newest = Artwork.objects.create(title='newest', image=upload(), category=self.series)
        self.assertGreater(newest.order, self.artwork.order)
        self.assertEqual(self.client.get('/pelagic/').context['page'][0].slug, newest.slug)

    def test_information_page_skips_the_list_and_opens_the_form(self):
        bio = Bio.objects.create(content='hello')
        self.assertRedirects(self.client.get('/admin/artworks/bio/'),
                             f'/admin/artworks/bio/{bio.pk}/change/')

    def test_category_list_explains_what_each_row_is(self):
        response = self.client.get('/admin/artworks/category/')
        self.assertContains(response, 'series inside Paintings')
        self.assertContains(response, 'see the page')

    def test_filename_becomes_a_readable_title(self):
        from .admin import ArtworkAdmin
        self.assertEqual(ArtworkAdmin.title_from_filename('Red-Garden_4.final.JPG'), 'red garden 4 final')


@override_settings(MEDIA_ROOT=MEDIA_ROOT, CONTACT_TO_EMAIL='',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ContactFormTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        Bio.objects.create(content='hello', email='bochettowalsh@example.com')

    def send(self, **overrides):
        data = {'name': 'A Collector', 'email': 'collector@example.com',
                'message': 'Is red pelagic still available?', 'website': ''}
        return self.client.post('/information/', {**data, **overrides}, follow=True)

    def test_form_appears_in_the_contact_section(self):
        response = self.client.get('/information/')
        self.assertContains(response, 'class="enquiry"')
        self.assertContains(response, 'name="message"')

    def test_message_is_stored_and_emailed_to_the_information_page_address(self):
        response = self.send()
        self.assertContains(response, 'your message has been sent')
        enquiry = ContactMessage.objects.get()
        self.assertEqual((enquiry.name, enquiry.email), ('A Collector', 'collector@example.com'))
        self.assertTrue(enquiry.emailed)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['bochettowalsh@example.com'])
        self.assertEqual(sent.reply_to, ['collector@example.com'])
        self.assertIn('red pelagic', sent.body)

    def test_explicit_recipient_setting_wins(self):
        with override_settings(CONTACT_TO_EMAIL='studio@example.com'):
            self.send()
        self.assertEqual(mail.outbox[0].to, ['studio@example.com'])

    def test_bad_address_is_rejected_and_nothing_is_sent(self):
        response = self.send(email='not-an-address')
        self.assertContains(response, 'valid email')
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_honeypot_submission_is_silently_dropped(self):
        response = self.send(website='http://spam.example')
        self.assertContains(response, 'your message has been sent')
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_repeated_submissions_are_throttled(self):
        for _ in range(5):
            self.send()
        response = self.send()
        self.assertContains(response, 'already sent a message')
        self.assertEqual(ContactMessage.objects.count(), 5)

    def test_a_delivery_failure_still_keeps_the_message(self):
        with patch('artworks.mail.EmailMessage.send', side_effect=OSError('smtp refused')):
            response = self.send()
        self.assertContains(response, 'your message has been sent')  # never show the visitor a failure
        enquiry = ContactMessage.objects.get()
        self.assertFalse(enquiry.emailed)  # flagged so it can be found in the admin

    def test_no_recipient_configured_does_not_break_the_page(self):
        Bio.objects.update(email='')
        response = self.send()
        self.assertContains(response, 'your message has been sent')
        self.assertFalse(ContactMessage.objects.get().emailed)
