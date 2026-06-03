from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        import core.signals

        # Monkeypatch AdminSite.get_app_list to dynamically separate CLICK Transactions into its own section
        from django.contrib import admin
        
        original_get_app_list = admin.AdminSite.get_app_list

        def custom_get_app_list(self, request, app_label=None):
            app_list = original_get_app_list(self, request, app_label)
            
            # Find the 'core' app dict in the app_list
            core_app = None
            for app in app_list:
                if app.get('app_label') == 'core':
                    core_app = app
                    break
                    
            if core_app:
                # Find and extract the 'ClickTransactions' model from core_app['models']
                click_model = None
                for model in core_app.get('models', []):
                    if model.get('object_name') == 'ClickTransactions':
                        click_model = model
                        break
                        
                if click_model:
                    # Remove from core models list
                    core_app['models'].remove(click_model)
                    
                    # Create or find a new app entry for 'CLICK'
                    click_app = None
                    for app in app_list:
                        if app.get('app_label') == 'click_custom':
                            click_app = app
                            break
                            
                    if not click_app:
                        click_app = {
                            'name': 'CLICK',
                            'app_label': 'click_custom',
                            'app_url': '/admin/click_custom/',
                            'has_module_perms': True,
                            'models': []
                        }
                        # Insert the new app right before 'payme' (to match Payme), or after 'core'
                        try:
                            payme_app = None
                            for app in app_list:
                                if app.get('app_label') == 'payme':
                                    payme_app = app
                                    break
                            if payme_app:
                                payme_index = app_list.index(payme_app)
                                app_list.insert(payme_index, click_app)
                            else:
                                core_index = app_list.index(core_app)
                                app_list.insert(core_index + 1, click_app)
                        except ValueError:
                            app_list.append(click_app)
                            
                    click_app['models'].append(click_model)
                    
            return app_list

        admin.AdminSite.get_app_list = custom_get_app_list

