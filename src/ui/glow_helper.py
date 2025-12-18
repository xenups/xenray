    def _update_horizon_glow(self, state: str):
        """
        Updates the horizon glow color based on state.
        state: 'connecting', 'connected', 'disconnected'
        """
        if state == "connecting":
            # Amber Glow
            self._earth_glow.gradient.colors = [
                ft.Colors.with_opacity(0.6, ft.Colors.AMBER_400),
                ft.Colors.with_opacity(0.1, ft.Colors.AMBER_600),
                ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
            ]
            self._earth_glow.opacity = 0.8
        
        elif state == "connected":
            # Purple Glow
            self._earth_glow.gradient.colors = [
                ft.Colors.with_opacity(0.5, ft.Colors.PURPLE_400),
                ft.Colors.with_opacity(0.1, ft.Colors.PURPLE_700),
                ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
            ]
            self._earth_glow.opacity = 0.5 # Base opacity, pulse will animate around this
            
        else: # disconnected
            # Hide or Blue (optional, sticking to hidden for now as per image)
            self._earth_glow.opacity = 0.0
            
        if self._earth_glow.page:
            self._earth_glow.update()
