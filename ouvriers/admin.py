from django.contrib import admin

from .models import Crew, Subcontractor, Trade, Worker, WorkerAssignment, WorkerCertification


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("matricule", "first_name", "last_name", "trade", "subcontractor", "status")
    list_filter = ("status", "trade", "subcontractor")
    search_fields = ("matricule", "first_name", "last_name", "phone")


@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "foreman", "is_active")
    filter_horizontal = ("members",)


admin.site.register([Trade, Subcontractor, WorkerCertification, WorkerAssignment])
