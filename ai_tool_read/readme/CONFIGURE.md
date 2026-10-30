To forbid a field, tick **AI Read Forbidden** on it. As the administrator, either:

- go to *Settings > Technical > Database Structure > Fields*, find the field and tick
  the flag (the **AI Read Forbidden** filter and list column help you review what is
  already flagged), or
- open the model in *Settings > Technical > Database Structure > Models* and tick the
  flag on the line of the field, in the *Fields* tab.

The flag applies to base fields as well as custom ones, and takes effect immediately. A
flag set on a mixin's field, such as `email_normalized` on `mail.thread.blacklist`,
applies to every model inheriting it.

A forbidden field takes along the fields that expose its value through their definition,
on any model: related fields, the fields a model delegates through `_inherits`, and
computed fields that depend on it. The `hidden` list returned by the **get_fields** tool
shows the result on a model. A value copied into another record when that record is
written is not followed (see *Known issues*): flag such fields as well.

This errs on the safe side: a computed field is hidden as soon as it depends on a
forbidden field, even when its value does not contain it. Forbidding `res.partner.email`
also hides `is_blacklisted`, a yes/no computed from the address, and
`hr.employee.mobile_phone`, computed by the same method as the work email. For the same
reason, flag the fields that hold the sensitive values themselves (email, phone,
address), not fields that many others are computed from, such as `parent_id` or
`company_id`: those would hide far more than intended.

Fields restricted to a user group (`groups=` in their definition) are already left out
of the results for a user outside that group, without any flag, and are not reported in
the `hidden` list either. **AI Read Forbidden** is only needed for fields that the user
is otherwise allowed to read.
