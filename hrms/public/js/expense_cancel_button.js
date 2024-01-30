function add_cancel_button(frm){
	if (frm.doc.docstatus == 0 && !frm.is_new()) {
		frm.add_custom_button(__("Cancel"), function() {
			if(frm.is_dirty()){
				frappe.throw("Save The Doc before Submitting it")
			}
			frm.call('cancel_doc')
			frm.reload_doc()
		});
	}
}