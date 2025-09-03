import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo-addons-oca-ai",
    description="Meta package for oca-ai Odoo addons",
    version=version,
    install_requires=[
        'odoo-addon-ai_oca_bridge>=16.0dev,<16.1dev',
        'odoo-addon-ai_oca_bridge_chatter>=16.0dev,<16.1dev',
        'odoo-addon-ai_oca_bridge_document_page>=16.0dev,<16.1dev',
        'odoo-addon-ai_oca_bridge_extra_parameters>=16.0dev,<16.1dev',
        'odoo-addon-ai_oca_bridge_helpdesk_mgmt>=16.0dev,<16.1dev',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 16.0',
    ]
)
