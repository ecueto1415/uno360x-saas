const templateDeleteButton = document.querySelector('[data-template-delete-open]');
if (templateDeleteButton) {
    const dialog = templateDeleteButton.parentElement.querySelector('.ua-template-dialog');
    templateDeleteButton.addEventListener('click', () => dialog.showModal());
    dialog.addEventListener('close', () => templateDeleteButton.focus());
}
