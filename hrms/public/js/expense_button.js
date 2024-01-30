function add_submit_button(frm){

    if(frm.doc.status==="Draft"){
        button_name="Send For Approval"
    }else{
        button_name="Approve"
    }

    var method = null;
    if(frm.doc.doctype==="Employee Advance"){
        method="hrms.overrides.custom_employee_advance.next_state"
    } else if(frm.doc.doctype==="Expense Claim"){
        method="hrms.overrides.custom_expense_claim.next_state"
    } else {
        frappe.throw(_("Unhandled doctype"));
    }

    frm.add_custom_button(__(button_name), function() {
        if(frm.is_dirty()){
            frappe.throw("Save The Doc before Submitting it")
        }
        frappe.call({
            method: method,
            args: {
                doc_name: frm.doc.name,
            },
            callback: function(r) {
                if (r.message) {
                    frm.reload_doc()
                    frappe.msgprint(__('Document Sent To The Approver Successfully'));
                }
            }
        });
    }).addClass("btn btn-primary btn-sm");
}