import re

from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ContactForm
from .mail import send_enquiry
from .models import Artwork, Bio, Category, SeriesTile

GALLERY_PAGE_SIZE = 30
ENQUIRY_LIMIT = 5          # per address below, per hour
ENQUIRY_LIMIT_WINDOW = 3600


def home(request):
    featured = Artwork.objects.filter(is_featured=True)
    return render(request, 'artworks/home.html', {'featured': featured})


def information(request):
    bio = Bio.objects.first()
    form = ContactForm(request.POST or None)
    if request.method == 'POST':
        if _too_many_enquiries(request):
            form.add_error(None, 'Thank you — you have already sent a message. '
                                 'Please email directly if it is urgent.')
        elif form.is_valid():
            if not form.looks_automated:
                enquiry = form.save()
                enquiry.emailed = send_enquiry(enquiry)
                enquiry.save(update_fields=['emailed'])
            messages.success(request, 'Thank you — your message has been sent.')
            return redirect(f"{reverse('information')}#contact")
    return render(request, 'artworks/information.html', {'bio': bio, 'form': form})


def _too_many_enquiries(request):
    """A light brake on repeated submissions from one address."""
    address = request.META.get('REMOTE_ADDR', '')
    if not address:
        return False
    key = f'enquiries:{address}'
    seen = cache.get(key, 0)
    if seen >= ENQUIRY_LIMIT:
        return True
    cache.set(key, seen + 1, ENQUIRY_LIMIT_WINDOW)
    return False


def section(request, slug):
    """A top-level category's mosaic of series covers."""
    category = get_object_or_404(Category, slug=slug, parent__isnull=True)
    if not category.is_section:
        return redirect(category, permanent=True)
    tiles = SeriesTile.objects.filter(category__parent=category).select_related('category')
    return render(request, 'artworks/section.html', {
        'section': category,
        'tiles': tiles,
        'current_section': category,
    })


def gallery(request, slug):
    category = Category.objects.filter(slug=slug).select_related('parent').first()
    if category is None:
        # WordPress had duplicate posts per series (/pelagic-2/, /pelagic-3/...), all the same gallery
        match = re.fullmatch(r'(.+)-\d+', slug)
        category = get_object_or_404(Category, slug=match.group(1)) if match else None
        if category is None:
            raise Http404
        return redirect(category, permanent=True)
    if category.is_section:
        return redirect(category, permanent=True)

    page = Paginator(category.artworks.all(), GALLERY_PAGE_SIZE).get_page(request.GET.get('page'))
    context = {
        'category': category,
        'page': page,
        'current_section': category.parent or category,
    }
    if request.headers.get('HX-Request'):
        return render(request, 'artworks/_gallery_items.html', context)
    return render(request, 'artworks/gallery.html', context)


def artwork_detail(request, slug):
    artwork = get_object_or_404(Artwork.objects.select_related('category__parent'), slug=slug)
    prev_artwork = next_artwork = None
    if artwork.category_id:
        siblings = list(artwork.category.artworks.values_list('slug', flat=True))
        index = siblings.index(artwork.slug)
        prev_artwork = siblings[index - 1] if index > 0 else None
        next_artwork = siblings[index + 1] if index < len(siblings) - 1 else None
    return render(request, 'artworks/artwork_detail.html', {
        'artwork': artwork,
        'prev_artwork': prev_artwork,
        'next_artwork': next_artwork,
        'current_section': artwork.category and (artwork.category.parent or artwork.category),
        'share_image': request.build_absolute_uri(artwork.image_display.url),
    })
