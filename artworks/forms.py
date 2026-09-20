"""Admin forms. Labels and help text are written for Joseph, not for a developer."""
from django import forms
from django.core.exceptions import ValidationError

from .models import Artwork, Bio, Category, ContactMessage

HELP = {
    'image': 'Any size. Smaller copies are made for you.',
    'category': 'Which gallery this belongs in.',
    'medium': 'e.g. ink, pigment, oil on cardboard',
    'dimensions': 'Height then width, e.g. 13" x 16"',
    'price': 'e.g. $750, sold, or contact for licensing and print',
    'description': 'Optional.',
    'is_featured': '',   # the label already says it
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
            'slug': 'The web address. Changing it breaks links people already have.',
            'parent': 'Leave empty for a menu heading of its own.',
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
            'exhibitions': 'One per line.',
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
        help_text='Each becomes its own artwork, named after its file.')
    category = forms.ModelChoiceField(
        queryset=Category.objects.select_related('parent').order_by('parent__order', 'order', 'name'),
        required=False, label='Gallery')
    medium = forms.CharField(max_length=200, required=False, label='Materials',
                             help_text='Applied to every picture in this batch.')
    price = forms.CharField(max_length=100, required=False, label='Price')


class MoveToGalleryForm(forms.Form):
    """Used by the "move to another gallery" bulk action."""
    category = forms.ModelChoiceField(
        queryset=Category.objects.select_related('parent').order_by('parent__order', 'order', 'name'),
        required=False, label='Move them to', help_text='Leave empty to take them off the site.')


class ContactForm(forms.ModelForm):
    """The enquiry form on the Information page."""
    # Bots fill in every field they find; people never see this one.
    website = forms.CharField(required=False, widget=forms.TextInput(
        attrs={'tabindex': '-1', 'autocomplete': 'off', 'aria-hidden': 'true'}))

    class Meta:
        model = ContactMessage
        fields = ('name', 'email', 'message')
        labels = {'name': 'Your name', 'email': 'Your email', 'message': 'Message'}
        widgets = {
            'name': forms.TextInput(attrs={'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'message': forms.Textarea(attrs={'rows': 6}),
        }

    @property
    def looks_automated(self):
        return bool(self.cleaned_data.get('website'))
