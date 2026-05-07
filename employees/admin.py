from django.contrib import admin

from .models import Department, Employee, EmployeeAuthorization, EmployeeContract, EmployeeSchedule, JobPosition


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("matricule", "first_name", "last_name", "company", "department", "position", "status")
    list_filter = ("status", "contract_type", "company", "department")
    search_fields = ("matricule", "first_name", "last_name", "email", "phone")
    raw_id_fields = ("user", "manager")
    filter_horizontal = ("authorized_sites",)


admin.site.register([Department, JobPosition, EmployeeContract, EmployeeAuthorization, EmployeeSchedule])
