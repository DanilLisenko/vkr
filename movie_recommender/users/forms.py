from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser

INPUT_ATTRS = {'class': 'form-control', 'style': 'background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);color:#f5f5f7;border-radius:10px;padding:12px 16px;'}

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'birth_date')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(INPUT_ATTRS)
        # Дата рождения — текстовое поле с маской ДД.ММ.ГГГГ
        self.fields['birth_date'].widget = forms.TextInput(
            attrs={
                **INPUT_ATTRS,
                'id': 'id_birth_date',
                'placeholder': 'ДД.ММ.ГГГГ',
                'maxlength': '10',
                'autocomplete': 'off',
            }
        )
        self.fields['birth_date'].required = False
        self.fields['birth_date'].input_formats = ['%d.%m.%Y', '%Y-%m-%d']

class CustomUserChangeForm(UserChangeForm):
    password = None

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'bio', 'birth_date', 'avatar')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if hasattr(field.widget, 'attrs'):
                field.widget.attrs.update(INPUT_ATTRS)