"""Módulo para cálculos físicos del agujero negro."""

import numpy as np


class SchwarzschildBlackHole:
    """Representa un agujero negro de Schwarzschild (no rotante)"""

    def __init__(self, mass: float):
        """
        Non-rotating Blackhole.

        Args:
            mass: Masa del agujero negro en masas solares.

        """
        self.G = 6.674e-11  # Constante gravitacional (m³/kg·s²)
        self.c = 299792458  # Velocidad de la luz (m/s)
        self.M_sun = 1.989e30  # Masa solar (kg)

        self.mass = mass * self.M_sun  # Masa en kg
        self.schwarzschild_radius = 2 * self.G * self.mass / (self.c**2)

    def deflection_angle_weak_field(self, impact_parameter: float) -> float:
        """
        Calcula el ángulo de deflexión en aproximación de campo débil.

        Args:
            impact_parameter: Distancia mínima del rayo al centro (m)

        Returns:
            Ángulo de deflexión en radianes

        """
        if impact_parameter < self.schwarzschild_radius:
            return np.inf  # El fotón es capturado

        # Fórmula de Einstein: α ≈ 4GM/(c²b)
        return 4 * self.G * self.mass / (self.c**2 * impact_parameter)

    def geodesic_equations(self, state: np.ndarray, affine_param: float) -> np.ndarray:
        """
        Ecuaciones geodésicas para fotones en métrica de Schwarzschild
        en coordenadas (t, r, θ, φ) y sus derivadas.

        Args:
            state: [t, r, θ, φ, dt/dλ, dr/dλ, dθ/dλ, dφ/dλ]
            affine_param: Parámetro afín λ

        Returns:
            Derivadas del estado

        """
        _t, r, theta, _phi, dt_dl, dr_dl, dtheta_dl, dphi_dl = state

        # Radio de Schwarzschild
        rs = self.schwarzschild_radius

        # Evitar singularidad en r = rs
        if r <= rs * 1.01:
            return np.zeros_like(state)

        # Componentes de la métrica
        f = 1 - rs / r

        # Símbolos de Christoffel (solo los no-nulos necesarios)
        # Γ^t_tr
        G_t_tr = rs / (2 * r * (r - rs))
        # Γ^r_tt
        G_r_tt = rs * f / (2 * r**2)
        # Γ^r_rr
        G_r_rr = -rs / (2 * r * (r - rs))
        # Γ^r_θθ
        G_r_thth = -(r - rs)
        # Γ^r_φφ
        G_r_phph = -(r - rs) * np.sin(theta) ** 2
        # Γ^θ_rθ
        G_th_rth = 1 / r
        # Γ^θ_φφ
        G_th_phph = -np.sin(theta) * np.cos(theta)
        # Γ^φ_rφ
        G_ph_rph = 1 / r
        # Γ^φ_θφ
        G_ph_thph = np.cos(theta) / np.sin(theta)

        # Ecuaciones geodésicas: d²x^μ/dλ² = -Γ^μ_αβ (dx^α/dλ)(dx^β/dλ)
        d2t_dl2 = -2 * G_t_tr * dt_dl * dr_dl

        d2r_dl2 = (
            -G_r_tt * dt_dl**2
            - G_r_rr * dr_dl**2
            - G_r_thth * dtheta_dl**2
            - G_r_phph * dphi_dl**2
        )

        d2theta_dl2 = -2 * G_th_rth * dr_dl * dtheta_dl - G_th_phph * dphi_dl**2

        d2phi_dl2 = (
            -2 * G_ph_rph * dr_dl * dphi_dl - 2 * G_ph_thph * dtheta_dl * dphi_dl
        )

        return np.array(
            [
                dt_dl,
                dr_dl,
                dtheta_dl,
                dphi_dl,
                d2t_dl2,
                d2r_dl2,
                d2theta_dl2,
                d2phi_dl2,
            ],
        )
