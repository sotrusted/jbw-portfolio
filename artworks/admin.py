import re
from pathlib import PurePath

from adminsortable2.admin import SortableAdminBase, SortableAdminMixin, SortableTabularInline
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from .forms import (ArtworkAdminForm, BioAdminForm, BulkUploadForm, CategoryAdminForm,
                    MoveToGalleryForm)
from .models import Artwork, Bio, Category, ContactMessage, SeriesTile

admin.site.site_header = 'Joseph Bochetto Walsh'
admin.site.site_title = 'Joseph Bochetto Walsh'
admin.site.index_title = 'What would you like to do?'
admin.site.index_template = 'admin/joe_index.html'  # extends the stock index, so it can't be named index.html


class AdminStyle:
    """Shared look: larger type, roomier controls, previews."""
    class Media:
        css = {'all': ('artworks/admin.css',)}


def preview(image, size=70, radius=4):
    if not image:
        return format_html('<span class="no-image">no picture</span>')
    return format_html(
        '<img src="{}" style="width:{}px;height:{}px;object-fit:cover;border-radius:{}px" alt="">',
        image.url, size, size, radius)


@admin.register(Artwork)
class ArtworkAdmin(SortableAdminMixin, AdminStyle, admin.ModelAdmin):
    form = ArtworkAdminForm
    list_display = ('thumbnail', 'title', 'category', 'medium', 'dimensions', 'price', 'is_featured')
    list_display_links = ('thumbnail', 'title')
    list_editable = ('medium', 'dimensions', 'price', 'is_featured')
    actions = ['move_to_gallery', 'show_on_front_page', 'remove_from_front_page']
    list_per_page = 100  # the largest gallery is 83 works, so one filtered page holds a whole gallery
    list_filter = ('category', 'is_featured', 'wall_view')
    search_fields = ('title', 'medium', 'category__name')
    exclude = ('slug',)
    ordering = ['-order']  # Default to descending order
    save_on_top = True

    def get_fieldsets(self, request, obj=None):
        has_picture = bool(obj and obj.image)
        return (
            (None, {'fields': (['title'] + (['big_preview'] if has_picture else [])
                               + ['image', 'category', 'is_featured'])}),
            ('Details shown beside the picture', {'fields': ('medium', 'dimensions', 'price', 'description')}),
            ('"View on wall"', {'fields': ['wall_view'] + (['wall_picker'] if has_picture else [])}),
            ('Exact position on the wall', {
                'classes': ('collapse',),
                'fields': ('wall_width', 'wall_left', 'wall_top'),
            }),
        )

    readonly_fields = ('big_preview', 'wall_picker')

    class Media(AdminStyle.Media):
        js = ('artworks/wall-picker.js',)

    @admin.display(description='')
    def thumbnail(self, obj):
        return preview(obj.image_thumb or obj.image)

    @admin.display(description='Picture now')
    def big_preview(self, obj):
        if not obj or not obj.image:
            return ''
        return format_html(
            '<a href="{}" target="_blank" rel="noopener"><img src="{}" class="big-preview" alt=""></a>'
            '<div class="hint-note">{} × {} pixels</div>',
            obj.image.url, (obj.image_display or obj.image).url, obj.width, obj.height)

    @admin.display(description='Position it')
    def wall_picker(self, obj):
        if not obj or not obj.image_thumb:
            return ''
        return render_to_string('admin/artworks/wall_picker.html', {
            'artwork': obj,
            'wall_small': static('artworks/wall-small.jpg'),
            'wall_large': static('artworks/wall-large.jpg'),
        })

    # -- bulk actions ----------------------------------------------------------------------

    @admin.action(description='Move selected artworks to another gallery\u2026')
    def move_to_gallery(self, request, queryset):
        form = MoveToGalleryForm(request.POST if 'apply' in request.POST else None)
        if 'apply' in request.POST and form.is_valid():
            category = form.cleaned_data['category']
            count = queryset.update(category=category)
            self.message_user(
                request,
                f'Moved {count} artworks to {category}.' if category
                else f'Took {count} artworks off the site (no gallery).',
                messages.SUCCESS)
            return None
        return render(request, 'admin/artworks/move_to_gallery.html', {
            **self.admin_site.each_context(request),
            'title': 'Move to another gallery',
            'artworks': queryset,
            'form': form,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'opts': self.opts,
        })

    @admin.action(description='Show selected on the front page')
    def show_on_front_page(self, request, queryset):
        self.message_user(request, f'{queryset.update(is_featured=True)} artworks now appear on the front page.')

    @admin.action(description='Remove selected from the front page')
    def remove_from_front_page(self, request, queryset):
        self.message_user(request, f'{queryset.update(is_featured=False)} artworks removed from the front page.')

    # -- adding several pictures at once ---------------------------------------------------

    def get_urls(self):
        return [path('bulk-upload/', self.admin_site.admin_view(self.bulk_upload),
                     name='artworks_artwork_bulk_upload')] + super().get_urls()

    def bulk_upload(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = BulkUploadForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            created = []
            for upload in form.cleaned_data['images']:
                artwork = Artwork(
                    title=self.title_from_filename(upload.name),
                    category=form.cleaned_data['category'],
                    medium=form.cleaned_data['medium'],
                    price=form.cleaned_data['price'],
                )
                artwork.image.save(upload.name, upload, save=True)
                created.append(artwork)
            if created:
                self.message_user(request, f'Added {len(created)} artworks. '
                                           'Fill in the details for each one below.', messages.SUCCESS)
                changelist = reverse('admin:artworks_artwork_changelist')
                category = form.cleaned_data['category']
                return redirect(f'{changelist}?category__id__exact={category.pk}' if category else changelist)
            form.add_error('images', 'No pictures were chosen.')
        return render(request, 'admin/artworks/bulk_upload.html', {
            **self.admin_site.each_context(request),
            'title': 'Add several artworks at once',
            'form': form,
            'opts': self.opts,
        })

    @staticmethod
    def title_from_filename(filename):
        """"red-garden-4.jpg" -> "red garden 4". Joseph can correct it afterwards."""
        stem = PurePath(filename).stem
        return re.sub(r'\s+', ' ', re.sub(r'[-_.]+', ' ', stem)).strip().lower()[:200]


class SeriesTileInline(SortableTabularInline):
    model = SeriesTile
    extra = 1
    fields = ('tile_preview', 'image', 'order')
    readonly_fields = ('tile_preview',)
    verbose_name = 'cover picture'
    verbose_name_plural = 'Cover pictures (shown on the menu page for this series)'

    @admin.display(description='')
    def tile_preview(self, obj):
        return preview(obj.image_thumb or obj.image, size=90)


@admin.register(Category)
class CategoryAdmin(SortableAdminBase, AdminStyle, admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = ('name', 'kind', 'slug', 'order', 'artwork_count', 'visit')
    list_editable = ('order',)
    list_filter = ('parent',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SeriesTileInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent').annotate(works=Count('artworks'))

    @admin.display(description='What it is')
    def kind(self, obj):
        if obj.parent_id:
            return f'series inside {obj.parent.name}'
        return 'menu heading' if obj.children.exists() else 'menu heading with its own gallery'

    @admin.display(description='Artworks', ordering='works')
    def artwork_count(self, obj):
        return obj.works

    @admin.display(description='')
    def visit(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">see the page &rarr;</a>',
                           obj.get_absolute_url())


@admin.register(Bio)
class BioAdmin(AdminStyle, admin.ModelAdmin):
    form = BioAdminForm
    fieldsets = (
        ("Artist's statement", {'fields': ('statement', 'statement_image', 'statement_banner')}),
        ('Biography', {'fields': ('content', 'biography_image', 'biography_banner')}),
        ('Exhibitions', {'fields': ('exhibitions',)}),
        ('Contact', {'fields': ('email', 'instagram')}),
    )
    save_on_top = True

    def has_add_permission(self, request):
        return not Bio.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """There is only ever one information page, so go straight to editing it."""
        page = Bio.objects.first()
        if page:
            return redirect('admin:artworks_bio_change', page.pk)
        return redirect('admin:artworks_bio_add')


@admin.register(ContactMessage)
class ContactMessageAdmin(AdminStyle, admin.ModelAdmin):
    """Enquiries are emailed to Joseph; this is the copy kept in case an email goes astray."""
    list_display = ('created_at', 'name', 'email', 'summary', 'handled', 'emailed')
    list_display_links = ('created_at', 'name')
    list_editable = ('handled',)
    list_filter = ('handled', 'emailed')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('name', 'email', 'message', 'created_at', 'emailed')
    fields = ('created_at', 'name', 'email', 'message', 'handled', 'emailed')

    @admin.display(description='Message')
    def summary(self, obj):
        return Truncator(obj.message).chars(70)

    def has_add_permission(self, request):
        return False
