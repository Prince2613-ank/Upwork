const form = document.querySelector('#login-form'), error = document.querySelector('#login-error');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  error.textContent = ''; button.disabled = true;
  try {
    const response = await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'pipeline-dashboard'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Could not sign in. Check your details.');
    form.elements.password.value = ''; window.location.replace('/');
  } catch (e) { error.textContent = e.message; button.disabled = false; }
});
