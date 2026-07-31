"""website URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.contrib.auth.views import LoginView
from cgen.forms import OrganizerLoginForm
from cgen import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('certificate/events/', views.events, name="events"),
    path('certificate/download/<int:certificate_id>/',
         views.certificate_download, name="certificate_download"),
    path('certificate/download/<int:certificate_id>/<str:email>/',
         views.certificate_download, name="certificate_download"),
    path('certificate/download_all/<int:certificate_id>/',
         views.certificate_download_all, name="certificate_download_all"),
    path('certificate/verify/', views.verify, name="verify"),
    path('certificate/verify/<str:key>/', views.verify, name="verify_key"),
    path('certificate/upload/<int:certificate_id>/',
         views.upload_csv_participants, name="upload"),
    path('organizer/dashboard/', views.organizer_dashboard,
         name='organizer_dashboard'),
    path('organizer/events/create/', views.create_event, name='create_event'),
    path('organizer/events/<int:event_id>/', views.event_detail, 
         name='event_detail'),
    path('organizer/events/<int:event_id>/edit/', views.edit_event,
         name='edit_event'),
    path('organizer/events/<int:event_id>/publish/', views.publish_event,
         name='publish_event'),
    path('organizer/events/<int:event_id>/unpublish/', views.unpublish_event,
         name='unpublish_event'),
    path('organizer/events/<int:event_id>/certificates/create/',
         views.create_certificate, name='create_certificate'),
    path('organizer/certificates/<int:certificate_id>/edit/',
         views.edit_certificate, name='edit_certificate'),
    path('organizer/certificates/<int:certificate_id>/participants/upload/',
         views.upload_csv_participants,
         name='upload_csv_participants'),
    path('organizer/certificates/<int:certificate_id>/test/',
         views.test_certificate_generation,
         name='test_certificate_generation'),
    path('organizer/certificates/<int:certificate_id>/bulk-download/',
         views.bulk_download_certificates, name='bulk_download_certificates'),
    path('organizer/certificates/<int:certificate_id>/participants/',
         views.participants, name='participants'),
    path('organizer/participants/<int:participant_id>/edit/',
         views.edit_participant, name='edit_participant'),
    path('organizer/participants/<int:participant_id>/delete/',
         views.delete_participant, name='delete_participant'),
    path('accounts/login/', LoginView.as_view(template_name='registration/login.html',
         authentication_form=OrganizerLoginForm), name='login'),
    path('accounts/logout/', views.organiser_logout, name='organiser_logout'),
    path('accounts/register/', views.organizer_register, name='register'),
]
