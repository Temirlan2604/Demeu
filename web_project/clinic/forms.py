from django import forms
from django.contrib.auth import authenticate
from .models import Appointment, Review, CustomUser, Patient


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ("phone", "last_name", "first_name", "patronymic", "password")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        Patient.objects.create(user=user)
        return user


class LoginForm(forms.Form):
    phone = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        user = authenticate(phone=data.get("phone"), password=data.get("password"))
        if not user:
            raise forms.ValidationError("Неверные данные")
        data["user"] = user
        return data


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ("doctor", "service", "date_time")
        widgets = {"date_time": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class ReviewForm(forms.ModelForm):
     class Meta:
         model = Review
         # теперь в форме только оценка и текстовые поля
         fields = ('rating', 'pros', 'cons')
         widgets = {
              'rating': forms.RadioSelect(),
              'pros': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Что понравилось?'}),
              'cons': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Что не понравилось?'}),
          }


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'phone')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'phone':      forms.TextInput(attrs={'class': 'form-control'}),
        }