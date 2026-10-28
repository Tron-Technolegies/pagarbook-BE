import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pagarlens.settings")
django.setup()

from datetime import date, time, timedelta
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import ProtectedError
from django.test import RequestFactory
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import force_authenticate

from authentication.models import Company, Staff
from authentication.views import delete_staff
from authentication.utils import company_or_error, is_management_user
from attendance.models import Attendance
from attendance.utils import late_threshold
from attendance.views import (
    attendance_summary,
    employee_attendance_report,
    daily_attendance_report,
    add_attendance,
    view_attendance,
    delete_attendance,
)
from devices.models import Device
from devices.views import add_device, delete_device, regenerate_device_key
from face_data.views import register_face_embedding


def test_issue_1():
    print("--- Testing Issue 1: Attendance Reporting & late_threshold ---")
    today = date(2026, 10, 13)
    thresh = late_threshold(today)
    assert thresh is not None, "late_threshold returned None"
    print("late_threshold for today:", thresh)

    with transaction.atomic():
        co = Company.objects.create(name="Issue 1 Test Co", email="issue1@test.com")
        u = User.objects.create_user(username="issue1_u", email="issue1@test.com", password="pass")
        st = Staff.objects.create(company=co, user=u, full_name="Tester", department="Management")
        emp1 = Staff.objects.create(company=co, full_name="Worker 1", employee_code="W001")
        
        # Check in on time (09:05)
        dt_on_time = timezone.make_aware(timezone.datetime(2026, 10, 13, 9, 5, 0))
        Attendance.objects.create(company=co, employee=emp1, attendance_type="check_in", timestamp=dt_on_time)
        dt_out = timezone.make_aware(timezone.datetime(2026, 10, 13, 17, 30, 0))
        Attendance.objects.create(company=co, employee=emp1, attendance_type="check_out", timestamp=dt_out)

        rf = RequestFactory()

        # 1. Summary report
        req = rf.get("/attendance/report/summary/?date=2026-10-13")
        force_authenticate(req, user=u)
        res = attendance_summary(req)
        assert res.status_code == 200, f"Summary failed: {res.status_code} {res.data}"
        assert res.data["present"] == 1, f"Expected 1 present, got {res.data['present']}"
        assert res.data["on_time"] == 1, f"Expected 1 on_time, got {res.data['on_time']}"
        print("Summary report response verified:", res.data)

        # 2. Employee report
        req2 = rf.get(f"/attendance/report/employee/{emp1.id}/?from=2026-10-13&to=2026-10-13")
        force_authenticate(req2, user=u)
        res2 = employee_attendance_report(req2, id=emp1.id)
        assert res2.status_code == 200, f"Employee report failed: {res2.status_code} {res2.data}"
        assert res2.data["totals"]["present"] == 1
        print("Employee report response verified:", res2.data["totals"])

        # 3. Daily report
        req3 = rf.get("/attendance/report/daily/?date=2026-10-13")
        force_authenticate(req3, user=u)
        res3 = daily_attendance_report(req3)
        assert res3.status_code == 200, f"Daily report failed: {res3.status_code} {res3.data}"
        assert res3.data["totals"]["present"] == 1
        print("Daily report response verified:", res3.data["totals"])

        transaction.set_rollback(True)
    print("Issue 1: PASS\n")


def test_issue_2():
    print("--- Testing Issue 2: Device Key Generation & Rotation ---")
    with transaction.atomic():
        co = Company.objects.create(name="Issue 2 Test Co", email="issue2@test.com")
        dev = Device.objects.create(company=co, name="Front Kiosk", device_id="KIOSK-001")
        
        # Test issue_new_key
        raw_key = dev.issue_new_key()
        assert raw_key is not None and len(raw_key) > 20
        assert dev.key_rotated_at is not None
        assert dev.check_key(raw_key) is True
        assert dev.check_key("wrong_key") is False
        print("Device key created and verified:", raw_key[:10] + "...")

        # Test API add_device and regenerate_device_key
        u = User.objects.create_user(username="issue2_u", email="issue2@test.com", password="pass")
        st = Staff.objects.create(company=co, user=u, full_name="Admin", department="Management")
        rf = RequestFactory()

        req = rf.post("/device/add/", {"name": "Gate 2", "device_id": "KIOSK-002", "location": "Gate"}, format="json")
        force_authenticate(req, user=u)
        res = add_device(req)
        assert res.status_code == 201, f"add_device failed: {res.status_code} {res.data}"
        assert "device_key" in res.data
        new_dev_id = res.data["data"]["id"]
        print("add_device API verified, key issued.")

        req2 = rf.post(f"/device/regenerate-key/{new_dev_id}/")
        force_authenticate(req2, user=u)
        res2 = regenerate_device_key(req2, id=new_dev_id)
        assert res2.status_code == 200, f"regenerate_device_key failed: {res2.status_code} {res2.data}"
        assert "device_key" in res2.data
        print("regenerate_device_key API verified.")

        transaction.set_rollback(True)
    print("Issue 2: PASS\n")


def test_issue_3():
    print("--- Testing Issue 3: Backward-Compatible Routes ---")
    # Verify Device URLs
    assert resolve("/device/add/").func == resolve("/device/device/add/").func
    assert resolve("/device/view/").func == resolve("/device/device/view/").func
    assert resolve("/device/auth/").func == resolve("/device/device/auth/").func
    assert resolve("/device/employees/").func == resolve("/device/device/employees/").func
    print("Device URLs resolve identical views (clean & legacy): PASS")

    # Verify Attendance URLs
    assert resolve("/attendance/add/").func == resolve("/attendance/attendance/add/").func
    assert resolve("/attendance/view/").func == resolve("/attendance/attendance/view/").func
    assert resolve("/attendance/report/summary/").func == resolve("/attendance/attendance/report/summary/").func
    assert resolve("/attendance/report/daily/").func == resolve("/attendance/attendance/report/daily/").func
    assert resolve("/attendance/sync/").func == resolve("/attendance/device/attendance/sync/").func
    print("Attendance URLs resolve identical views (clean & legacy): PASS")

    # Verify Face URLs
    assert resolve("/face/embedding/register/").func == resolve("/face/face/embedding/register/").func
    assert resolve("/face/device/face-data/").func is not None
    print("Face URLs resolve identical views (clean & legacy): PASS")
    print("Issue 3: PASS\n")


def test_issue_4():
    print("--- Testing Issue 4: Prevent Accidental Deletion of Attendance History ---")
    with transaction.atomic():
        co = Company.objects.create(name="Issue 4 Test Co", email="issue4@test.com")
        u = User.objects.create_user(username="issue4_u", email="issue4@test.com", password="pass")
        admin_st = Staff.objects.create(company=co, user=u, full_name="Admin", department="Management")
        emp = Staff.objects.create(company=co, full_name="Worker With History", employee_code="W400")
        att = Attendance.objects.create(company=co, employee=emp, attendance_type="check_in", timestamp=timezone.now())

        # Test 1: ORM ProtectedError
        try:
            emp.delete()
            assert False, "emp.delete() should have raised ProtectedError!"
        except ProtectedError:
            print("Direct ORM delete correctly blocked by ProtectedError.")

        assert Attendance.objects.filter(id=att.id).exists() is True

        # Test 2: delete_staff API endpoint
        rf = RequestFactory()
        req = rf.delete(f"/auth/staff/delete/{emp.id}/")
        force_authenticate(req, user=u)
        res = delete_staff(req, id=emp.id)
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        assert "Cannot delete staff with existing attendance records" in res.data["message"]
        print("delete_staff API correctly rejected deletion with HTTP 400:", res.data["message"])

        assert Attendance.objects.filter(id=att.id).exists() is True
        print("Attendance history remains fully intact.")

        transaction.set_rollback(True)
    print("Issue 4: PASS\n")


def test_issue_5():
    print("--- Testing Issue 5: Role-Based Access, Deactivation & Missing Staff Handlers ---")
    with transaction.atomic():
        co = Company.objects.create(name="Issue 5 Test Co", email="issue5@test.com")

        # 1. User without Staff profile
        u_no_staff = User.objects.create_user(username="nostaff_u", email="nostaff@test.com", password="pass")
        rf = RequestFactory()
        
        req = rf.get("/attendance/view/")
        force_authenticate(req, user=u_no_staff)
        res = view_attendance(req)
        assert res.status_code == 404, f"Expected 404 for user without staff, got {res.status_code}"
        assert res.data["message"] == "Staff record not found"
        print("User without staff accessing attendance/view: HTTP 404 correctly returned without 500 crash.")

        req_f = rf.post("/face/embedding/register/", {"employee_id": 1, "embedding": [0.1, 0.2]}, format="json")
        force_authenticate(req_f, user=u_no_staff)
        res_f = register_face_embedding(req_f)
        assert res_f.status_code == 404
        print("User without staff accessing face/embedding/register: HTTP 404 correctly returned without 500 crash.")

        # 2. Deactivated Staff member
        u_deact = User.objects.create_user(username="deact_u", email="deact@test.com", password="pass")
        st_deact = Staff.objects.create(company=co, user=u_deact, full_name="Deactivated Employee", is_active=False, department="Management")
        
        req_d = rf.get("/attendance/view/")
        force_authenticate(req_d, user=u_deact)
        res_d = view_attendance(req_d)
        assert res_d.status_code == 403, f"Expected 403 for deactivated staff, got {res_d.status_code}"
        assert res_d.data["message"] == "Your account has been deactivated."
        print("Deactivated staff accessing attendance/view: HTTP 403 correctly returned.")

        # 3. Non-management staff trying admin actions
        u_regular = User.objects.create_user(username="regular_u", email="regular@test.com", password="pass")
        st_regular = Staff.objects.create(company=co, user=u_regular, full_name="Sales Staff", is_active=True, department="Sales")
        
        dev = Device.objects.create(company=co, name="Office Kiosk", device_id="KIOSK-REG")

        # Try to delete device as regular staff
        req_reg_dev = rf.delete(f"/device/delete/{dev.id}/")
        force_authenticate(req_reg_dev, user=u_regular)
        res_reg_dev = delete_device(req_reg_dev, id=dev.id)
        assert res_reg_dev.status_code == 403, f"Expected 403, got {res_reg_dev.status_code}"
        assert "Management access required" in res_reg_dev.data["message"]
        print("Non-management staff attempting delete_device: HTTP 403 correctly blocked.")

        # Try to delete staff as regular staff
        target_emp = Staff.objects.create(company=co, full_name="Target", employee_code="T001")
        req_reg_staff = rf.delete(f"/auth/staff/delete/{target_emp.id}/")
        force_authenticate(req_reg_staff, user=u_regular)
        res_reg_staff = delete_staff(req_reg_staff, id=target_emp.id)
        assert res_reg_staff.status_code == 403
        print("Non-management staff attempting delete_staff: HTTP 403 correctly blocked.")

        # 4. Management staff CAN perform admin actions
        u_mgr = User.objects.create_user(username="mgr_u", email="mgr@test.com", password="pass")
        st_mgr = Staff.objects.create(company=co, user=u_mgr, full_name="Manager", is_active=True, department="Management")

        req_mgr = rf.delete(f"/auth/staff/delete/{target_emp.id}/")
        force_authenticate(req_mgr, user=u_mgr)
        res_mgr = delete_staff(req_mgr, id=target_emp.id)
        assert res_mgr.status_code == 200, f"Expected 200 for management staff, got {res_mgr.status_code} {res_mgr.data}"
        print("Management staff performing delete_staff: HTTP 200 succeeded.")

        transaction.set_rollback(True)
    print("Issue 5: PASS\n")


if __name__ == "__main__":
    test_issue_1()
    test_issue_2()
    test_issue_3()
    test_issue_4()
    test_issue_5()
    print("ALL 5 ISSUES TESTED AND PASSED SUCCESSFULLY!")
