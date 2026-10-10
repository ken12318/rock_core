from django.contrib import admin
from django.urls import path

from core_app import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="dashboard"),
    path("history/", views.history_page, name="history"),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("api/predict/", views.predict_image, name="predict_image"),
    path("api/history/", views.history_api, name="history_api"),
    path("api/history/delete/", views.delete_history, name="delete_history"),
    path("api/history/clear/", views.clear_history, name="clear_history"),
    path("api/export/docx/", views.export_docx, name="export_docx"),
    path("api/export/history-xlsx/", views.export_history_xlsx, name="export_history_xlsx"),
]
