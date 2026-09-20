from django.contrib import admin
from django.utils.html import format_html
from .models import Artwork, Bio, Category, SeriesTile
from adminsortable2.admin import SortableAdminBase, SortableAdminMixin, SortableTabularInline

admin.site.site_header = 'Joseph Bochetto Walsh'
admin.site.site_title = 'Joseph Bochetto Walsh'
admin.site.index_title = 'Site content'


@admin.register(Artwork)
class ArtworkAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ('thumbnail', 'title', 'category', 'medium', 'dimensions', 'price', 'is_featured')
    list_display_links = ('thumbnail', 'title')
    list_per_page = 50
    list_filter = ('category', 'is_featured', 'wall_view')
    search_fields = ('title', 'medium', 'category__name')
    exclude = ('slug',)
    ordering = ['-order']  # Default to descending order
    fieldsets = (
        (None, {'fields': ('title', 'image', 'category', 'is_featured')}),
        ('Details', {'fields': ('medium', 'dimensions', 'price', 'description')}),
        ('View on wall', {
            'classes': ('collapse',),
            'fields': ('wall_view', 'wall_width', 'wall_left', 'wall_top'),
        }),
    )

    def thumbnail(self, obj):
        if obj.image:
            url = obj.image_thumb.url if obj.image_thumb else obj.image.url
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />', url)
        return "No Image"
    thumbnail.short_description = 'Thumbnail'


class SeriesTileInline(SortableTabularInline):
    model = SeriesTile
    extra = 0
    fields = ('image', 'order')


@admin.register(Category)
class CategoryAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ('__str__', 'slug', 'layout', 'order', 'artwork_count')
    list_editable = ('order',)
    list_filter = ('parent',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SeriesTileInline]

    def artwork_count(self, obj):
        return obj.artworks.count()
    artwork_count.short_description = 'Artworks'


@admin.register(Bio)
class BioAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'last_updated')

    def has_add_permission(self, request):
        return not Bio.objects.exists()
