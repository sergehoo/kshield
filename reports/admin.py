from django.contrib import admin

from .models import Dashboard, DashboardWidget, KPISnapshot, Report, ReportRun, ReportSchedule

admin.site.register([Report, ReportRun, ReportSchedule, KPISnapshot, Dashboard, DashboardWidget])
