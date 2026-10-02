from django import forms

from .models import Post


class UploadForm(forms.Form):
    media = forms.FileField(label="Фото или видео")
    title = forms.CharField(label="Название", max_length=140, required=False)
    visibility = forms.ChoiceField(choices=Post.Visibility.choices, initial=Post.Visibility.LINK)
