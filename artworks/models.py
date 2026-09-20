import uuid
from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from PIL import Image, ImageOps


def build_rendition(source, max_px, quality=85):
    """Return (ContentFile, (width, height)) for a JPEG no larger than max_px on its long side."""
    source.open('rb')
    try:
        img = ImageOps.exif_transpose(Image.open(source))
        full_size = img.size
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGBA')
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        img.thumbnail((max_px, max_px), Image.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True, progressive=True)
    finally:
        source.seek(0)
    return ContentFile(buffer.getvalue()), full_size


class Category(models.Model):
    """A top-level section (Paintings, Photography...) or a series inside one (pelagic, jellies...)."""
    LAYOUT_TILES = 'tiles'
    LAYOUT_MASONRY = 'masonry'
    LAYOUT_CHOICES = [
        (LAYOUT_TILES, 'Square tiles, 3 columns'),
        (LAYOUT_MASONRY, 'Uncropped, 2 columns'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children',
                               help_text='Leave empty for a top-level section shown in the main menu.')
    layout = models.CharField(max_length=10, choices=LAYOUT_CHOICES, default=LAYOUT_TILES)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return f"{self.parent.name} / {self.name}" if self.parent_id else self.name

    @property
    def is_section(self):
        """Top-level categories with series underneath get a tile page instead of a gallery."""
        return self.parent_id is None and self.children.exists()

    def get_absolute_url(self):
        if self.is_section:
            return reverse('section', kwargs={'slug': self.slug})
        return reverse('gallery', kwargs={'slug': self.slug})


class Artwork(models.Model):
    WALL_NONE = ''
    WALL_SMALL = 'small'
    WALL_LARGE = 'large'
    WALL_CHOICES = [
        (WALL_NONE, "Don't offer"),
        (WALL_SMALL, 'Close-up wall (smaller works)'),
        (WALL_LARGE, 'Wide room (larger works)'),
    ]

    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='artworks/', width_field='width', height_field='height')
    image_display = models.ImageField(upload_to='artworks/display/', blank=True, editable=False)
    image_thumb = models.ImageField(upload_to='artworks/thumb/', blank=True, editable=False)
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)
    slug = models.SlugField(unique=True, blank=True, max_length=200)
    medium = models.CharField(max_length=200, blank=True, help_text='e.g. ink, pigment, oil on cardboard')
    dimensions = models.CharField(max_length=100, blank=True, help_text='e.g. 13" x 16"')
    price = models.CharField(max_length=100, blank=True, help_text='e.g. $750, sold, NFS')
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='artworks')
    created_at = models.DateTimeField(auto_now_add=True)
    is_featured = models.BooleanField(default=False, help_text='Show in the home page slideshow.')
    wall_view = models.CharField('"View on wall"', max_length=5, choices=WALL_CHOICES, blank=True, default=WALL_LARGE)
    # Placement of the work on the wall photo, as percentages of the photo's width / height.
    wall_width = models.DecimalField(max_digits=5, decimal_places=2, default=24,
                                     help_text='Width of the work, as % of the wall photo width.')
    wall_left = models.DecimalField(max_digits=5, decimal_places=2, default=32,
                                    help_text="Left edge, as % of the wall photo width.")
    wall_top = models.DecimalField(max_digits=5, decimal_places=2, default=26.67,
                                   help_text="Top edge, as % of the wall photo height.")
    order = models.PositiveIntegerField(default=0, db_index=True, blank=False, null=False)

    class Meta:
        ordering = ['-order']  # Changed to descending order

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            prefix = self.category.name if self.category_id else 'work'
            self.slug = slugify(f"{prefix}-{self.title}-{str(uuid.uuid4())[:8]}")
        if not self.pk and not self.order:
            # a newly added work goes to the top of its gallery, which sorts by -order
            self.order = (type(self).objects.aggregate(models.Max('order'))['order__max'] or 0) + 1
        if self.image and (self._image_changed() or not self.image_thumb):
            self._build_renditions()
        super().save(*args, **kwargs)

    def _image_changed(self):
        if not self.pk:
            return True
        stored = type(self).objects.filter(pk=self.pk).values_list('image', flat=True).first()
        return stored != self.image.name

    def _build_renditions(self):
        stem = PurePosixPath(self.image.name).stem
        for field, max_px in ((self.image_display, 1800), (self.image_thumb, 800)):
            content, _ = build_rendition(self.image, max_px)
            field.save(f"{stem}.jpg", content, save=False)

    def get_absolute_url(self):
        return reverse('artwork_detail', kwargs={'slug': self.slug})


class SeriesTile(models.Model):
    """A cover image on a section page. A series may have several, to fill out the mosaic."""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='tiles',
                                 limit_choices_to={'parent__isnull': False})
    image = models.ImageField(upload_to='tiles/')
    image_thumb = models.ImageField(upload_to='tiles/thumb/', blank=True, editable=False)
    order = models.PositiveIntegerField(default=0, db_index=True, blank=False, null=False)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.category.name} tile"

    def save(self, *args, **kwargs):
        if self.image and not (self.pk and self.image_thumb and
                               type(self).objects.filter(pk=self.pk, image=self.image.name).exists()):
            content, _ = build_rendition(self.image, 800)
            self.image_thumb.save(f"{PurePosixPath(self.image.name).stem}.jpg", content, save=False)
        super().save(*args, **kwargs)


class Bio(models.Model):
    """Everything on the Information page. Only the first row is used."""
    statement = models.TextField("artist's statement", blank=True)
    content = models.TextField('biography')
    exhibitions = models.TextField(blank=True, help_text='One per line.')
    email = models.EmailField(blank=True)
    instagram = models.CharField(max_length=100, blank=True, help_text='Handle only, without the @')
    statement_image = models.ImageField(upload_to='information/', blank=True)
    statement_banner = models.ImageField(upload_to='information/', blank=True)
    biography_image = models.ImageField(upload_to='information/', blank=True)
    biography_banner = models.ImageField(upload_to='information/', blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'information page'
        verbose_name_plural = 'information page'

    def __str__(self):
        return 'Information page'


class ContactMessage(models.Model):
    """An enquiry from the website. Kept here as well as emailed, so nothing is ever lost."""
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    emailed = models.BooleanField(default=False)
    handled = models.BooleanField('replied to', default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'enquiry'
        verbose_name_plural = 'enquiries'

    def __str__(self):
        return f'{self.name} <{self.email}>'
