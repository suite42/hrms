class RoleConstants:
    EXPENSE_APPROVER1_ROLE = "L1 Expense Approver"
    EXPENSE_APPROVER2_ROLE = "L2 Expense Approver"
    HR_L1_EXPENSE_ROLE = "HR L1 Expense Approver"
    HR_L2_EXPENSE_ROLE = "HR L2 Expense Approver"
    FINANCE_ROLE = "Finance Team Expense Approver"
    OFFICE_ADMIN_ROLE = "Office Admin Expense Approver"
    EXPENSE_AMOUNT = 5000
    ADVANCE_AMOUNT = 5000
    EXPENSE_APPROVE_DATE = 5


class CompanyConstants:
    S42_IDR = "PT. ONE SUITE TECHNOLOGIES"
    SUITE42 = "One Suite Technologies Private Limited"
    KOTAK_BANK = "Kotak Mahindra Bank"
    REIMBURSEMENT_BANK_ACCOUNT = ["5946999821"]
    PAYABLE_ACCOUNTS = {
        "PT. ONE SUITE TECHNOLOGIES": {
            "advance_payable_account": "Employee Advances - S42_IDR",
            "reimbursement_payable_account": "Reimbursement Payable - S42_IDR",
        },
        "One Suite Technologies Private Limited": {
            "advance_payable_account": "Employee Advances - Suite42",
            "reimbursement_payable_account": "Reimbursement Payable - Suite42",
        },
    }


class TaskTypeConstatns:
    APPROVE_EXPENSE_CLAIM = "Approve Expense Claim"
    APPROVE_EMPLOYEE_ADVANCE = "Approve Employee Advance"
    OPEN = "Open"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    ONHOLD = "OnHold"


class EmployeeConstant:
    EMPLOYEMENT_TYPE = ["Intern", "Full-time", "Probation"]
    CONTRACT_EMPLOYEE_TYPE = "Contract"


class ExpenseCategoryConstants:
    BUSSINESS_EXP = "Business Expenses"
    OFFICE_AND_ADMIN_EXP = "Office maintenance and Admin Expenses"
    EMPLOYEE_ENG_EXP = "Employee Engagement Expense"


class ExpenseClaimConstants:
    DRAFT = "Draft"
    PENDING_APPROVAL = "Pending Approval"
    PENDING_APPROVAL_BY_ADMIN = "Pending Approval By Admin"
    PENDING_APPROVAL_BY_HR_L1 = "Pending Approval By HR L1"
    PENDING_APPROVAL_BY_HR_L2 = "Pending Approval By HR L2"
    PENDING_PURCHASE_INVOICE = "Pending Purchase Invoice"
    PURCHASE_INVOICE_LINKED = "Purchase Invoice Linked"
    PENDING_PAYMENT = "Pending Payment"
    CANCELLED = "Cancelled"
    PAID = "Paid"


class EmployeeAdvanceConstants:
    DRAFT = "Draft"
    PENDING_APPROVAL = "Pending Approval"
    PENDING_APPROVAL_BY_ADMIN = "Pending Approval By Admin"
    PENDING_APPROVAL_BY_HR = "Pending Approval By HR"
    PENDING_PAYMENT = "Pending Payment"
    CLAIMED = "Claimed"
    PARTLY_CLAIMED = "Partly Claimed"
    CANCELLED = "Cancelled"
    PAID = "Paid"
