// Validation utilities for registration form
const ValidationMessages = {
    requiredFields: 'Please fill out all required fields.',
    emailInvalid: 'Please enter a valid email address.',
    phoneInvalid: 'Please enter a valid phone number.',
    passwordLength: 'Password must be at least 8 characters long.',
    passwordMismatch: 'Passwords do not match.',
    captchaRequired: 'Please complete the captcha challenge.'
};

function validateRegistrationForm(form, credential, useIdentityProvider = false) {
    const required = ['firstname', 'lastname', 'email', 'address1', 'city', 'state', 'postal_code', 'phone_number'];
    for (const field of required) {
        const value = form[field];
        if (!value || !value.toString().trim()) {
            alert(ValidationMessages.requiredFields);
            return false;
        }
    }
    const emailPattern = /^[^@]+@[^@]+\.[^@]+$/;
    if (!emailPattern.test(form.email)) {
        alert(ValidationMessages.emailInvalid);
        return false;
    }
    const phonePattern = /^[0-9()+\s-]{7,20}$/;
    if (!phonePattern.test(form.phone_number)) {
        alert(ValidationMessages.phoneInvalid);
        return false;
    }
    if (!useIdentityProvider) {
        if (credential.password.length < 8) {
            alert(ValidationMessages.passwordLength);
            return false;
        }
    }
    return true;
}
