from django import forms
from .models import Review

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'review_text']
        labels = {
            'rating': 'Оценка:',
            'review_text': 'Ваш отзыв:'
        }
        widgets = {
            'rating': forms.NumberInput(attrs={
                'min': 1, 'max': 10,
                'class': 'form-control',
                'placeholder': 'Оценка от 1 до 10'
            }),
            'review_text': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Введите отзыв (не обязательно)...'
            }),
        }