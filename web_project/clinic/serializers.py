from rest_framework import serializers
from .models import CustomUser, Doctor, Patient, Service, Appointment


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = '__all__'


class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.__str__', read_only=True)

    class Meta:
        model = Doctor
        fields = ('id', 'full_name', 'specialization')


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = '__all__'
