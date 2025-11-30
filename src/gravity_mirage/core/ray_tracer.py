"""Ray tracing para visualización de lensing gravitacional."""

import numpy as np
from scipy.integrate import solve_ivp

from gravity_mirage.core.physics import SchwarzschildBlackHole


class GravitationalRayTracer:
    """Implementa ray tracing considerando efectos gravitacionales."""

    def __init__(self, black_hole: SchwarzschildBlackHole):
        self.bh = black_hole

    def trace_photon_simple(
        self,
        initial_pos: np.ndarray,
        initial_dir: np.ndarray,
        max_distance: float = 1000,
    ) -> np.ndarray:
        """
        Traza un fotón usando aproximación de campo débil (más rápido).

        Args:
            initial_pos: Posición inicial [x, y] (en unidades de Rs)
            initial_dir: Dirección inicial normalizada [dx, dy]
            max_distance: Distancia máxima a trazar

        Returns:
            Array de posiciones [N, 2]

        """
        pos = np.array(initial_pos, dtype=float)
        direction = np.array(initial_dir, dtype=float)
        direction = direction / np.linalg.norm(direction)

        positions = [pos.copy()]
        step_size = 0.1 * self.bh.schwarzschild_radius

        for _ in range(int(max_distance / step_size)):
            # Distancia al agujero negro
            r = np.linalg.norm(pos)

            # Si está muy cerca, es capturado
            if r < 1.1 * self.bh.schwarzschild_radius:
                break

            # Calcular deflexión
            # Componente radial hacia el agujero negro
            radial_dir = -pos / r

            # Fuerza de deflexión proporcional a 1/r²
            deflection_strength = (self.bh.schwarzschild_radius / r) ** 2
            deflection = radial_dir * deflection_strength * 0.1

            # Actualizar dirección
            direction = direction + deflection
            direction = direction / np.linalg.norm(direction)

            # Avanzar posición
            pos = pos + direction * step_size
            positions.append(pos.copy())

            # Si se aleja demasiado, terminar
            if r > max_distance:
                break

        return np.array(positions)

    def trace_photon_geodesic(
        self,
        initial_pos_spherical: tuple[float, float, float],
        initial_velocity: tuple[float, float, float],
        lambda_max: float = 100,
    ) -> object:
        """
        Traza un fotón resolviendo ecuaciones geodésicas completas
        (más preciso pero más lento)

        Args:
            initial_pos_spherical: (r, θ, φ) posición inicial
            initial_velocity: (dr/dλ, dθ/dλ, dφ/dλ) velocidades iniciales
            lambda_max: Parámetro afín máximo

        Returns:
            Solución de las ecuaciones geodésicas

        """
        r0, theta0, phi0 = initial_pos_spherical
        dr0, dtheta0, dphi0 = initial_velocity

        # Condición inicial para dt/dλ (de la condición de fotón: g_μν dx^μ dx^ν = 0)
        rs = self.bh.schwarzschild_radius
        f = 1 - rs / r0
        dt0 = np.sqrt(
            (dr0**2 / f + r0**2 * (dtheta0**2 + np.sin(theta0) ** 2 * dphi0**2)) / f,
        )

        # Estado inicial: [t, r, θ, φ, dt/dλ, dr/dλ, dθ/dλ, dφ/dλ]
        state0 = np.array([0, r0, theta0, phi0, dt0, dr0, dtheta0, dphi0])

        # Resolver ecuaciones geodésicas.
        # Use an event to stop integration once the photon returns to a large
        # radius close to the starting radius (i.e. after passing the
        # closest-approach and escaping). This avoids requiring an excessively
        # large fixed lambda_max while still capturing the scattering angle.
        lambda_span = (0.0, float(lambda_max))

        r0 = initial_pos_spherical[0]
        # threshold slightly below the start radius to avoid immediately
        # triggering at t=0
        threshold = r0 * 0.999

        def escape_event(_lam, s):
            # s is the state vector: [t, r, theta, phi, dt/dλ, dr/dλ, dθ/dλ, dφ/dλ]
            return s[1] - threshold

        # only trigger when r is increasing through the threshold (escaping)
        escape_event.terminal = True
        escape_event.direction = 1

        solution = solve_ivp(
            lambda lam, s: self.bh.geodesic_equations(s, lam),
            lambda_span,
            state0,
            method="RK45",
            rtol=1e-8,
            events=[escape_event],
            dense_output=True,
        )

        # If the event fired, evaluate the dense solution at the event time so
        # callers get the final state at escape. Otherwise return the raw
        # solution (may be truncated if lambda_max was too small).
        if solution.t_events and len(solution.t_events[0]) > 0:
            t_event = float(solution.t_events[0][0])
            y_event = solution.sol(t_event)
            # Append the event time/state to the existing OdeResult so callers
            # can access the final state at escape using the usual attributes.
            solution.t = np.append(solution.t, t_event)
            solution.y = np.hstack([solution.y, y_event.reshape(-1, 1)])
            return solution

        return solution
