// Force-layout configuration for the 3D graph (react-force-graph-3d).

export const GRAPH_CONFIG = {
  nodeRelSize: 6,
  cooldownTicks: 200,
  d3AlphaDecay: 0.015,
  d3VelocityDecay: 0.3,
  // link force tuning
  linkDistance: 60,
  linkStrength: 0.6,
  chargeStrength: -180,
  collideRadius: 12,
  // glow ring for high-severity nodes
  glowPulseDuration: 1200, // ms
  enableGlowForSeverities: ['CRITICAL', 'HIGH'] as const,
};

export const CAMERA_DISTANCE = 180;