from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.growth.views import unsubscribe_page

admin.site.site_header = f"{settings.PLATFORM_NAME} Admin"
admin.site.site_title = f"{settings.PLATFORM_NAME} Admin"
admin.site.index_title = "Platform management"

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("tickets/", include("apps.tickets.urls")),
    path("scanner/", include("apps.checkin.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.growth.urls")),
    path("organizations/", include("apps.organizations.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("t/", include("apps.tickets.page_urls")),
    path("u/<str:token>/", unsubscribe_page, name="unsubscribe"),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
