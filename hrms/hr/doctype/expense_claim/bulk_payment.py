import frappe
from frappe import _
import pandas as pd
import json
from datetime import datetime
from io import StringIO
import requests

from apps.hrms.hrms.suite42_utils.common_functions import (
    user_has_role,
    handle_exceptions_with_readable_message,
)

from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_party_details,
    get_account_details,
)
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

from hrms.suite42_utils.reimbursement_constants import (
    RoleConstants,
    ExpenseClaimConstants,
    CompanyConstants,
)
from frappe_s3_attachment.controller import get_public_file_url


@frappe.whitelist()
@handle_exceptions_with_readable_message
def bulk_payment(url):
    file_url = get_public_file_url(url)
    response = requests.get(file_url)
    csv_data = StringIO(response.content.decode("utf-8"))

    df = pd.read_csv(
        csv_data,
        dtype={
            "Sending Account Number": "string",
            "Receiver Name": "string",
            "Receiver Code": "string",
            "Product Code": "string",
            "Package Code": "string",
            "IFSC Code": "string",
            "Receiver Account Number": "string",
            "Amount": "string",
            "Instrument Date": "string",
            "Effective Date": "string",
            "UTR SrNo": "string",
            "Instrument No": "string",
            "Instrument Status": "string",
            "Maker": "string",
            "Maker DateTime": "string",
            "Checker 1": "string",
            "Checker 1 DateTime": "string",
            "Checker 2": "string",
            "Checker 2 DateTime": "string",
            "Sent By": "string",
            "Sent By DateTime": "string",
            "Instrument Payment Ref No": "string",
            "Batch Payment Ref No": "string",
            "Payment Details": "string",
            "Payment Details 2": "string",
            "Payment Details 3": "string",
            "Payment Details 4": "string",
            "Host Processing Date & Time": "string",
            "Reject Remarks": "string",
            "Debit Type": "string",
        },
    )

    if not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE):
        frappe.throw(
            _(f"Invalid permission, only user with role {RoleConstants.FINANCE_ROLE} is allowed")
        )

    payment_entry_list = []
    for index, row in df.iterrows():
        paid_amount = float(row["Amount"])
        actual_paid_amount = 0

        employee_doc = None
        expense_claim_dict = json.loads(row["Payment Details"])
        expense_claim_list = expense_claim_dict.get("expense_claims")

        refrence_list = []
        paid_to = None
        for expense_claim in expense_claim_list:
            expense_claim_doc = frappe.get_doc("Expense Claim", expense_claim)

            if paid_to and paid_to != expense_claim_doc.payable_account:
                frappe.throw(
                    _("Expense Claim Accounts Are not same for the Receiver {} ").format(
                        row["Receiver Name"]
                    )
                )
            else:
                paid_to = expense_claim_doc.payable_account

            if not employee_doc:
                employee_doc = frappe.get_doc("Employee", expense_claim_doc.employee)

            remaining_amount = (
                expense_claim_doc.grand_total - expense_claim_doc.total_amount_reimbursed
            )

            if remaining_amount > paid_amount:
                frappe.throw(
                    _(
                        f"Paid amount is less than the remaining amount for the expense claim {expense_claim}"
                    )
                )

            refrence_entry = {
                "reference_doctype": "Expense Claim",
                "reference_name": expense_claim_doc.name,
                "total_amount": remaining_amount,
                "outstanding_amount": remaining_amount,
                "allocated_amount": remaining_amount,
                "parentfield": "references",
                "parenttype": "Payment Entry",
                "docstatus": 1,
                "doctype": "Payment Entry Reference",
            }

            refrence_list.append(refrence_entry)
            actual_paid_amount += remaining_amount
            paid_amount = paid_amount - remaining_amount

        if actual_paid_amount != float(row["Amount"]):
            frappe.throw(_(f"Paid Amount not matching with the expense claim amount"))

        party_details = get_party_details(
            employee_doc.company, "Employee", employee_doc.name, frappe.utils.nowdate()
        )

        if row["Sending Account Number"] not in CompanyConstants.REIMBURSEMENT_BANK_ACCOUNT:
            frappe.throw(_(f"Account Number added is not supported currently"))

        company_bank_account_exists = frappe.db.get_list(
            "Bank Account",
            filters={
                "currency": "INR",
                "is_company_account": 1,
                "company": CompanyConstants.SUITE42,
                "bank_account_no": row["Sending Account Number"],
            },
            pluck="name",
        )

        if not company_bank_account_exists:
            frappe.throw(_(f"For Company {CompanyConstants.SUITE42} No INR Bank Account present"))
        else:
            # Currently Allowing only One Account
            company_bank_account_doc = frappe.get_doc(
                "Bank Account", company_bank_account_exists[0]
            )

        bank_cash_account = frappe.get_doc("Account", company_bank_account_doc.account).name

        bank_account_currency = company_bank_account_doc.currency

        paid_to_account_currency = get_account_details(paid_to, frappe.utils.nowdate()).get(
            "account_currency"
        )
        refrence_date = datetime.strptime(row["Maker DateTime"].split(" ")[0], "%d/%m/%Y").date()
        payment_entry_doc = frappe.get_doc(
            {
                "doctype": "Payment Entry",
                "docstatus": 1,
                "payment_type": "Pay",
                "mode_of_payment": row["Product Code"],
                "party_type": "Employee",
                "party": employee_doc.name,
                "party_name": employee_doc.employee_name,
                "paid_from": bank_cash_account,
                "paid_from_account_currency": bank_account_currency,
                "paid_to": paid_to,
                "paid_to_account_currency": paid_to_account_currency,
                "paid_amount": actual_paid_amount,
                "total_allocated_amount": actual_paid_amount,
                "received_amount": actual_paid_amount,
                "unallocated_amount": 0,
                "references": refrence_list,
                "reference_no": row["UTR SrNo"],
                "reference_date": refrence_date,
            }
        )
        payment_entry_doc.insert(ignore_permissions=True).name
        for expense_claim in expense_claim_list:
            expense_claim_doc = frappe.get_doc("Expense Claim", expense_claim)
            expense_claim_doc.is_paid = 1
            expense_claim_doc.status = ExpenseClaimConstants.PAID
            expense_claim_doc.total_amount_reimbursed = expense_claim_doc.grand_total
            expense_claim_doc.save(ignore_permissions=True)
