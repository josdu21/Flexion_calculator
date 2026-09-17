"""Motores de diseño según AASHTO LRFD Bridge Design Specifications, 9.ª ed. (2020).

Alcance implementado: secciones rectangulares de **concreto reforzado**
(sin preesfuerzo), en flexión, cortante y torsión. El cortante usa el
**procedimiento simplificado** de §5.7.3.4.1 (β = 2.0, θ = 45°); el
procedimiento general de §5.7.3.4.2 (MCFT) no está implementado.

Las ecuaciones se escriben en la forma SI que publica la propia norma
(N, mm, MPa), no convertidas desde ksi.
"""
