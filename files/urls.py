from django.urls import path
from . import views

app_name = 'files'

urlpatterns = [
    path('patient/<int:patient_pk>/upload/', views.attachment_upload, name='upload'),
    path('<int:pk>/download/', views.attachment_download, name='download'),
    path('<int:pk>/delete/', views.attachment_delete, name='delete'),
]
