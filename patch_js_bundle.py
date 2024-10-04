"""
Helper script which verifies that there is one _app....js file in the .web/_static/_next/static/chunks/pages/ dir that
contains the string '"ws://${BACKEND_DOMAIN_AND_PORT}/_event","uk":"http://${BACKEND_DOMAIN_AND_PORT}/_upload"}'
and it also patches the protocols, according to whether the BACKEND_USE_SSL env var is set to true or false.
"""

import os

# Expect non-SSL protocols by default
EXPECTED_CONTENT = '"ws://${BACKEND_DOMAIN_AND_PORT}/_event","uk":"http://${BACKEND_DOMAIN_AND_PORT}/_upload"}'
PATCHED_CONTENT = '"ws${BACKEND_PROTOCOL_SECURE_SUFFIX}://${BACKEND_DOMAIN_AND_PORT}/_event","uk":"http${BACKEND_PROTOCOL_SECURE_SUFFIX}://${BACKEND_DOMAIN_AND_PORT}/_upload"}'

if __name__ == '__main__':
    pages_dir = os.path.join('.web', '_static', '_next', 'static', 'chunks', 'pages')
    if not os.path.isdir(pages_dir):
        raise FileNotFoundError(f'The {pages_dir} directory does not exist!')

    app_js_file = [f for f in os.listdir(pages_dir) if f.startswith('_app') and f.endswith('.js')][0]
    app_js_file_path = os.path.join(pages_dir, app_js_file)

    with open(app_js_file_path, 'r', encoding="utf-8") as f:
        content = f.read()

    if EXPECTED_CONTENT not in content:
        raise ValueError(f'The {app_js_file_path} file does not contain the expected content!')

    patched_content = content.replace(EXPECTED_CONTENT, PATCHED_CONTENT)

    # Write the patched content back to the _app....js file and append a suffix, for Nginx's envsubst mechanism
    template_js_file_path = app_js_file_path + '.template'  # ".template" is the default of NGINX_ENVSUBST_TEMPLATE_SUFFIX
    with open(template_js_file_path, 'wt', encoding="utf-8") as f:
        f.write(patched_content)

    os.unlink(app_js_file_path)

    print(f'Patched the {app_js_file_path} file successfully!')
