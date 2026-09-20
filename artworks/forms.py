"""Admin forms. Labels and help text are written for Joseph, not for a developer."""
from django import forms
from django.core.exceptions import ValidationError

from .models import Artwork, Bio, Category

HELP = {
    'title': 'Shown under the picture, e.g. <em>red pelagic</em>. Lowercase is fine.',
    'image': 'Upload the largest version you have. The site makes its own smaller copies '
             'automatically, so you never need to resize anything first.',
    'category': 'Which gallery this belongs in. Leave empty to keep it off the site for now.',
    'is_featured': 'Ticked works take turns on the front page.',
    'medium': 'Materials, e.g. <em>ink, pigment, oil on cardboard</em>.',
    'dimensions': 'Height then width, e.g. <em>13" x 16"</em>.',
    'price': 'Anything you like: <em>$750</em>, <em>sold</em>, or <em>contact for licensing and print</em>. '
             'Leave empty to show no price.',
    'description': 'Optional. A few sentences shown under the details.',
}


class ArtworkAdminForm(forms.ModelForm):
    class Meta:
        model = Artwork
        fields = '__all__'
        labels = {
            'image': 'Picture',
            'category': 'Gallery',
            'is_featured': 'Show on the front page',
            'medium': 'Materials',
            'dimensions': 'Size',
            'price': 'Price',
            'wall_view': 'Offer "view on wall"',
            'wall_width': 'Width on the wall (%)',
            'wall_left': 'Distance from the left (%)',
            'wall_top': 'Distance from the top (%)',
        }
        help_texts = HELP

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'category' in self.fields:
            self.fields['category'].queryset = Category.objects.select_related('parent').order_by(
                'parent__order', 'order', 'name')


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = '__all__'
        labels = {'parent': 'Part of', 'layout': 'How the pictures are arranged'}
        help_texts = {
            'name': 'Shown as the gallery heading, e.g. <em>pelagic</em>.',
            'slug': 'The web address, e.g. <em>pelagic</em> gives josephbochettowalsh.com/pelagic/. '
                    'Changing this breaks any link people already have.',
            'parent': 'Leave empty for a menu heading (Paintings, Drawings...). '
                      'Otherwise pick the menu heading this series sits under.',
            'order': 'Smaller numbers come first.',
        }


class BioAdminForm(forms.ModelForm):
    class Meta:
        model = Bio
        fields = '__all__'
        labels = {'content': 'Biography', 'statement_image': 'Photo beside the statement',
                  'statement_banner': 'Wide picture under the statement',
                  'biography_image': 'Picture beside the biography',
                  'biography_banner': 'Wide picture under the biography'}
        help_texts = {
            'statement': 'Leave a blank line between paragraphs.',
            'content': 'Leave a blank line between paragraphs.',
            'exhibitions': 'One per line, e.g. <em>2016 Paintings, Sedi Studios, Los Angeles</em>.',
            'instagram': 'Just the handle, without the @.',
        }


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file input that accepts several files at once (Django's FileField takes only one)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'accept': 'image/*'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            if not data and self.required:  # an empty list would otherwise skip validation
                raise ValidationError(self.error_messages['required'], code='required')
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class BulkUploadForm(forms.Form):
    """Add a batch of pictures at once; details can be filled in afterwards."""
    images = MultipleFileField(
        label='Pictures',
        help_text='Choose as many as you like. Each becomes its own artwork, named after its file.')
    category = forms.ModelChoiceField(
        queryset=Category.objects.select_related('parent').order_by('parent__order', 'order', 'name'),
        required=False, label='Gallery', help_text='Put them all in this gallery.')
    medium = forms.CharField(max_length=200, required=False, label='Materials',
                             help_text='Optional. Applied to every picture in this batch.')
    price = forms.CharField(max_length=100, required=False, label='Price',
                            help_text='Optional. Applied to every picture in this batch.')
