from django.contrib import admin

from .models import DetectionHistory


admin.site.site_header = "岩心智能识别系统后台"
admin.site.site_title = "岩心识别后台"
admin.site.index_title = "数据管理中心"


@admin.register(DetectionHistory)
class DetectionHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "rock_type", "porosity", "permeability", "created_at")
    list_filter = ("rock_type", "created_at")
    search_fields = ("user__username", "rock_type")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 20
