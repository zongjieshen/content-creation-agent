// Configuration Editor Functionality
document.addEventListener('DOMContentLoaded', () => {
    setupConfigEditor();
});

function setupConfigEditor() {
    const configEditorBtn = document.getElementById('config-editor-btn');
    const configEditorModal = document.getElementById('config-editor-modal');
    const modalClose = configEditorModal.querySelector('.modal-close');
    const saveConfigBtn = document.getElementById('save-config-changes');
    
    // Initialize CodeMirror
    let editor = null;
    
    // Open modal and load config
    configEditorBtn.addEventListener('click', async () => {
        try {
            showLoading(true);
            const response = await fetch(`${API_BASE_URL}/get_config`);
            if (response.ok) {
                const data = await response.json();
                
                // Initialize CodeMirror if not already initialized
                if (!editor) {
                    editor = CodeMirror(document.getElementById('config-editor'), {
                        value: data.config_content,
                        mode: 'yaml',
                        theme: 'monokai',
                        lineNumbers: true,
                        indentUnit: 2,
                        tabSize: 2,
                        lineWrapping: true,
                        extraKeys: {
                            "Tab": function(cm) {
                                if (cm.somethingSelected()) {
                                    cm.indentSelection("add");
                                } else {
                                    cm.replaceSelection(" ".repeat(cm.getOption("indentUnit")));
                                }
                            }
                        }
                    });
                } else {
                    editor.setValue(data.config_content);
                }
                
                configEditorModal.style.display = 'block';
                // Refresh editor to ensure proper rendering
                setTimeout(() => editor.refresh(), 10);
            } else {
                throw new Error('Failed to load configuration');
            }
        } catch (error) {
            console.error('Error loading config:', error);
            alert('Failed to load configuration. Please try again.');
        } finally {
            showLoading(false);
        }
    });
    
    // Close modal
    modalClose.addEventListener('click', () => {
        configEditorModal.style.display = 'none';
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', (event) => {
        if (event.target === configEditorModal) {
            configEditorModal.style.display = 'none';
        }
    });
    
    // Save config changes
    saveConfigBtn.addEventListener('click', async () => {
        try {
            if (!editor) {
                throw new Error('Editor not initialized');
            }
            
            showLoading(true);
            const response = await fetch(`${API_BASE_URL}/save_config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    config_content: editor.getValue()
                })
            });
            
            if (response.ok) {
                alert('Configuration saved successfully!');
                configEditorModal.style.display = 'none';
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save configuration');
            }
        } catch (error) {
            console.error('Error saving config:', error);
            alert(`Failed to save configuration: ${error.message}`);
        } finally {
            showLoading(false);
        }
    });
}