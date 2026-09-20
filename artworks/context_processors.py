from django.db.models import Count

from .models import Category


def navigation(request):
    sections = Category.objects.filter(parent__isnull=True).annotate(series_count=Count('children'))
    return {'nav_sections': sections}
