import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { PointCloudFrame } from "../types/signalforge";

const SEM_COLORS: Record<number, number> = {
  0: 0x3a3a3a, // ground
  1: 0x3b82f6, // vehicle
  2: 0xf59e0b, // pedestrian
  3: 0x22c55e, // cyclist
  4: 0xa855f7, // animal
  5: 0x94a3b8, // static
};

interface Props {
  frame: PointCloudFrame | null;
  showRadar?: boolean;
}

export function PointCloudViewer({ frame, showRadar = true }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<{
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    renderer: THREE.WebGLRenderer;
    controls: OrbitControls;
    points: THREE.Points | null;
    radar: THREE.Points | null;
    boxes: THREE.Group;
    anim: number;
  } | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      mount.innerHTML = '<div style="padding:1rem;color:#8fa3b8">WebGL unavailable</div>';
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0f14);

    const camera = new THREE.PerspectiveCamera(
      60,
      mount.clientWidth / Math.max(mount.clientHeight, 1),
      0.1,
      300
    );
    camera.position.set(-15, 20, 15);
    camera.up.set(0, 0, 1);
    camera.lookAt(10, 0, 0);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(15, 0, 0);
    controls.update();

    const grid = new THREE.GridHelper(80, 40, 0x1e293b, 0x15202b);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);

    // Ego marker
    const egoGeom = new THREE.BoxGeometry(4.5, 1.9, 1.5);
    const egoMat = new THREE.MeshBasicMaterial({ color: 0x22d3ee, wireframe: true });
    const egoMesh = new THREE.Mesh(egoGeom, egoMat);
    egoMesh.position.set(0, 0, 0.75);
    scene.add(egoMesh);

    const boxes = new THREE.Group();
    scene.add(boxes);

    const light = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(light);

    let anim = 0;
    const tick = () => {
      anim = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    const onResize = () => {
      if (!mount) return;
      camera.aspect = mount.clientWidth / Math.max(mount.clientHeight, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
    };
    window.addEventListener("resize", onResize);

    stateRef.current = {
      scene,
      camera,
      renderer,
      controls,
      points: null,
      radar: null,
      boxes,
      anim,
    };

    return () => {
      cancelAnimationFrame(anim);
      window.removeEventListener("resize", onResize);
      controls.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      stateRef.current = null;
    };
  }, []);

  useEffect(() => {
    const st = stateRef.current;
    if (!st || !frame) return;

    // Clear previous points
    if (st.points) {
      st.scene.remove(st.points);
      st.points.geometry.dispose();
      (st.points.material as THREE.Material).dispose();
      st.points = null;
    }
    if (st.radar) {
      st.scene.remove(st.radar);
      st.radar.geometry.dispose();
      (st.radar.material as THREE.Material).dispose();
      st.radar = null;
    }
    while (st.boxes.children.length) {
      const c = st.boxes.children.pop()!;
      st.boxes.remove(c);
      if (c instanceof THREE.LineSegments) {
        c.geometry.dispose();
        (c.material as THREE.Material).dispose();
      }
    }

    const n = Math.floor(frame.xyz.length / 3);
    if (n > 0) {
      const positions = new Float32Array(frame.xyz);
      const colors = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        const sem = frame.semantic[i] ?? 0;
        const hex = SEM_COLORS[sem] ?? 0xaaaaaa;
        const r = ((hex >> 16) & 255) / 255;
        const g = ((hex >> 8) & 255) / 255;
        const b = (hex & 255) / 255;
        const inten = frame.intensity[i] ?? 0.5;
        const boost = 0.45 + 0.55 * inten;
        colors[i * 3] = r * boost;
        colors[i * 3 + 1] = g * boost;
        colors[i * 3 + 2] = b * boost;
      }
      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const mat = new THREE.PointsMaterial({
        size: 0.12,
        vertexColors: true,
        sizeAttenuation: true,
      });
      st.points = new THREE.Points(geom, mat);
      st.scene.add(st.points);
    }

    if (showRadar && frame.radar_xyz.length >= 3) {
      const rp = new Float32Array(frame.radar_xyz);
      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.BufferAttribute(rp, 3));
      const mat = new THREE.PointsMaterial({
        size: 0.55,
        color: 0xff4d6d,
        sizeAttenuation: true,
      });
      st.radar = new THREE.Points(geom, mat);
      st.scene.add(st.radar);
    }

    for (const box of frame.boxes) {
      const edges = new THREE.EdgesGeometry(
        new THREE.BoxGeometry(box.length, box.width, box.height)
      );
      const color =
        box.occlusion > 0.6 ? 0xf97316 : box.category === "pedestrian" ? 0xfbbf24 : 0x60a5fa;
      const line = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9 })
      );
      line.position.set(box.x, box.y, box.z);
      line.rotation.z = (box.heading_deg * Math.PI) / 180;
      st.boxes.add(line);
    }
  }, [frame, showRadar]);

  return <div ref={mountRef} className="viewer-canvas" />;
}
