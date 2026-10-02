from django.urls import path

from . import views

app_name = "photos"
urlpatterns = [
    path("", views.feed, name="feed"),
    path("upload/", views.upload, name="upload"),
    path("mine/", views.mine, name="mine"),
    path("reports/", views.reports, name="reports"),
    path("login/", views.staff_login, name="login"),
    path("logout/", views.staff_logout, name="logout"),
    path("p/<str:slug>/moderate/", views.moderate, name="moderate"),
    path("p/<str:slug>/", views.post_detail, name="post"),
    path("p/<str:slug>/edit/", views.post_update, name="update"),
    path("p/<str:slug>/reset/", views.post_reset_link, name="reset"),
    path("p/<str:slug>/delete/", views.post_delete, name="delete"),
    path("p/<str:slug>/report/", views.post_report, name="report"),
    path("i/<str:slug>/", views.media_file, name="media"),
    path("i/<str:slug>/thumb/", views.media_file, {"kind": "thumb"}, name="thumb"),
]
