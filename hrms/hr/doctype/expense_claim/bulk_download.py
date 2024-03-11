import frappe
from frappe import _
from frappe.utils.csvutils import build_csv_response
import pandas as pd
from apps.hrms.hrms.suite42_utils.common_functions import (
    user_has_role,
    handle_exceptions_with_readable_message,
)
from hrms.suite42_utils.reimbursement_constants import (
    RoleConstants,
    ExpenseClaimConstants,
    CompanyConstants,
    EmployeeConstant,
)

import json
from datetime import datetime


@frappe.whitelist()
@handle_exceptions_with_readable_message
def bulk_download(company, account):
    if company != CompanyConstants.SUITE42:
        frappe.throw(_(f"Currently Only for Company {CompanyConstants.SUITE42} is supported"))

    company_bank_account_doc = frappe.get_doc("Bank Account", account)

    if (
        not company_bank_account_doc.is_company_account
        or company_bank_account_doc.bank_account_no
        not in CompanyConstants.REIMBURSEMENT_BANK_ACCOUNT
    ):
        frappe.throw(_("Company bank account selected is not supported"))

    expense_claim_list = []
    if not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE):
        frappe.throw(
            _(f"Invalid permission, only user with role {RoleConstants.FINANCE_ROLE} is allowed")
        )

    employee_list = frappe.db.get_list(
        "Employee",
        filters={
            "status": "active",
            "employment_type": ["in", EmployeeConstant.EMPLOYEMENT_TYPE],
            "company": CompanyConstants.SUITE42,
        },
        pluck="name",
        ignore_permissions=True,
    )

    for employee_name in employee_list:
        pending_expense_claims = frappe.db.get_list(
            "Expense Claim",
            filters={
                "employee": employee_name,
                "status": ExpenseClaimConstants.PENDING_PAYMENT,
                "grand_total": (">", 0),
            },
            fields=["name", "grand_total"],
        )
        if not pending_expense_claims:
            continue

        total_amount = 0
        expense_claim_names = []
        for row in pending_expense_claims:
            expense_claim_names.append(row.get("name"))
            total_amount += row.get("grand_total")

        employee_doc = frappe.get_doc("Employee", employee_name)

        # Employee Bank Acccount
        employee_bank_account_exists = frappe.db.get_list(
            "Bank Account",
            filters={
                "currency": "INR",
                "company": employee_doc.company,
                "party_type": "Employee",
                "party": employee_name,
            },
            pluck="name",
        )

        if not employee_bank_account_exists:
            frappe.throw(_(f"For Employee {employee_name} No INR Bank Account present"))
        elif len(employee_bank_account_exists) > 1:
            frappe.throw(_(f"For Employee {employee_name} More than one bank account exists"))
        else:
            employee_bank_account_doc = frappe.get_doc(
                "Bank Account", employee_bank_account_exists[0]
            )

        # create Rows
        payment_type = ""
        if employee_bank_account_doc.bank == CompanyConstants.KOTAK_BANK:
            payment_type = "IFT"  # Payment_Type
        elif total_amount > 1000000:
            payment_type = "RTGS"  # Payment_Type
        else:
            payment_type = "NEFT"  # Payment_Type

        expense_claims = {"expense_claims": expense_claim_names}
        expense_claim_row = {
            "Client_Code": "OSTPCMS",
            "Product_Code": "RPAY",
            "Payment_Type": payment_type,
            "Payment_Ref_No": "",
            "Payment_Date": datetime.now().date().strftime("%d/%m/%Y"),
            "Instrument Date": "",
            "Dr_Ac_No": company_bank_account_doc.bank_account_no,
            "Amount": total_amount,
            "Bank_Code_Indicator": "M",
            "Beneficiary_Code": "",
            "Beneficiary_Name": employee_bank_account_doc.account_name,
            "Beneficiary_Bank": employee_bank_account_doc.bank,
            "Beneficiary_Branch / IFSC Code": employee_bank_account_doc.ifsc,
            "Beneficiary_Acc_No": employee_bank_account_doc.bank_account_no,
            "Location": "",
            "Print_Location": "",
            "Instrument_Number": "",
            "Ben_Add1": "",
            "Ben_Add2": "",
            "Ben_Add3": "",
            "Ben_Add4": "",
            "Beneficiary_Email": "",
            "Beneficiary_Mobile": "",
            "Credit_Narration": "trf from onesuite",
            "Payment Details 1": json.dumps(expense_claims),
            "Payment Details 2": "",
            "Payment Details 3": "",
            "Payment Details 4": "",
        }
        expense_claim_list.append(expense_claim_row)

    csv_headers = [
        "Client_Code",
        "Product_Code",
        "Payment_Type",
        "Payment_Ref_No",
        "Payment_Date",
        "Instrument Date",
        "Dr_Ac_No",
        "Amount",
        "Bank_Code_Indicator",
        "Beneficiary_Code",
        "Beneficiary_Name",
        "Beneficiary_Bank",
        "Beneficiary_Branch / IFSC Code",
        "Beneficiary_Acc_No",
        "Location",
        "Print_Location",
        "Instrument_Number",
        "Ben_Add1",
        "Ben_Add2",
        "Ben_Add3",
        "Ben_Add4",
        "Beneficiary_Email",
        "Beneficiary_Mobile",
        "Credit_Narration",
        "Payment Details 1",
        "Payment Details 2",
        "Payment Details 3",
        "Payment Details 4",
    ]

    data = []
    data.append(csv_headers)

    for expense_claim in expense_claim_list:
        rows = [expense_claim.get(key) for key in csv_headers]
        data.append(rows)

    build_csv_response(data, "Pending_expense_claims")
