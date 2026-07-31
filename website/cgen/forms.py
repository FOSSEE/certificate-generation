from django import forms
from .models import Event, Certificate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class OrganizerLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Username'
    }))

    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': 'Password'
    }))

    error_messages = {
        'invalid_login': (
            'Invalid username/password, or your account is not approved yet.'
        ),
        'inactive': (
            'Your account is pending admin approval.'
        ),
    }


class OrganizerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'description', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'start_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
       }


class CertificateForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = ['description', 'template_type', 'template', 'background', 'variables']
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'template_type': forms.Select(attrs={'class': 'form-select'}),
            'template': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'background': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'variables': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
