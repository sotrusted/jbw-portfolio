# artworks/urls.py
# Paths mirror the old WordPress permalinks so existing links and search results keep working.

from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('information/', views.information, name='information'),
    path('category/<slug:slug>/', views.section, name='section'),
    path('portfolio/<slug:slug>/', views.artwork_detail, name='artwork_detail'),

    # old WordPress pages that no longer have a page of their own
    path('welcome/', RedirectView.as_view(pattern_name='home', permanent=True)),
    path('home-page/', RedirectView.as_view(pattern_name='home', permanent=True)),
    path('portfolio/', RedirectView.as_view(pattern_name='home', permanent=True)),
    path('artists-statement/', RedirectView.as_view(url='/information/#artist', permanent=True)),

    # keep last: /pelagic/, /surface-design/, /mixed-media/ ...
    path('<slug:slug>/', views.gallery, name='gallery'),
]
