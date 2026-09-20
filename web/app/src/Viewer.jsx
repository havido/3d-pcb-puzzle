// 3D view of the converted board. The STL is one solid, so it is split by height:
// triangles that sit entirely above the base are the copper, the rest is the plate.
import { OrbitControls } from '@react-three/drei'
import { Canvas, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'

const COPPER = '#d9822b'
const PLATE = '#d8d2c4'

function splitByHeight(geometry, zSplit) {
  const pos = geometry.getAttribute('position').array
  const base = [], copper = []
  for (let i = 0; i < pos.length; i += 9) {
    const zmin = Math.min(pos[i + 2], pos[i + 5], pos[i + 8])
    ;(zmin >= zSplit - 1e-4 ? copper : base).push(...pos.slice(i, i + 9))
  }
  const make = (arr) => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3))
    g.computeVertexNormals()
    return g
  }
  return { base: make(base), copper: make(copper) }
}

function Board({ url, zSplit, showPlate, showCopper, sliceZ, onBounds }) {
  const [parts, setParts] = useState(null)
  const plane = useMemo(() => new THREE.Plane(new THREE.Vector3(0, 0, -1), 0), [])
  plane.constant = sliceZ

  useEffect(() => {
    let alive = true
    fetch(url)
      .then((r) => r.arrayBuffer())
      .then((buf) => {
        if (!alive) return
        const geo = new STLLoader().parse(buf)
        geo.computeBoundingBox()
        onBounds(geo.boundingBox.clone())
        setParts(splitByHeight(geo, zSplit))
      })
    return () => { alive = false }
  }, [url, zSplit])

  if (!parts) return null
  const clip = sliceZ > 0 ? [plane] : []
  return (
    <group>
      {showPlate && (
        <mesh geometry={parts.base} castShadow receiveShadow>
          <meshStandardMaterial color={PLATE} roughness={0.85} metalness={0} clippingPlanes={clip} side={THREE.DoubleSide} />
        </mesh>
      )}
      {showCopper && (
        <mesh geometry={parts.copper}>
          <meshStandardMaterial color={COPPER} roughness={0.35} metalness={0.75} clippingPlanes={clip} side={THREE.DoubleSide} />
        </mesh>
      )}
    </group>
  )
}

// Points the camera at the board and, when a warning is picked, flies to it.
function Rig({ bounds, focus }) {
  const controls = useRef()
  const { camera } = useThree()
  useEffect(() => {
    if (!bounds) return
    const c = bounds.getCenter(new THREE.Vector3())
    const size = bounds.getSize(new THREE.Vector3())
    const d = Math.max(size.x, size.y) * 1.5
    camera.position.set(c.x - d * 0.35, c.y - d * 0.75, c.z + d * 0.8)
    camera.near = 0.1
    camera.far = d * 20
    camera.updateProjectionMatrix()
    controls.current?.target.copy(c)
    controls.current?.update()
  }, [bounds, camera])
  useEffect(() => {
    if (!focus || !controls.current) return
    controls.current.target.set(focus.x, -focus.y, 0)
    controls.current.update()
  }, [focus])
  return <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.12} />
}

function Marker({ focus, top }) {
  if (!focus) return null
  return (
    <mesh position={[focus.x, -focus.y, top + 2]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[2.5, 0.4, 8, 32]} />
      <meshBasicMaterial color="#d62728" />
    </mesh>
  )
}

export default function Viewer({ jobUrl, zSplit, focus }) {
  const [bounds, setBounds] = useState(null)
  const [showPlate, setShowPlate] = useState(true)
  const [showCopper, setShowCopper] = useState(true)
  const [sliceZ, setSliceZ] = useState(0)
  const top = bounds ? bounds.max.z : 3

  return (
    <div className="viewer">
      <Canvas
        dpr={[1, 2]}
        camera={{ fov: 40, position: [0, -200, 160] }}
        onCreated={({ gl }) => { gl.localClippingEnabled = true }}
      >
        <color attach="background" args={['#11161d']} />
        <hemisphereLight intensity={0.7} groundColor="#20262e" />
        <directionalLight position={[80, -120, 220]} intensity={2.2} />
        <directionalLight position={[-140, 60, 90]} intensity={0.6} />
        {jobUrl && (
          <Board url={jobUrl} zSplit={zSplit} showPlate={showPlate} showCopper={showCopper}
                 sliceZ={sliceZ} onBounds={setBounds} />
        )}
        <Marker focus={focus} top={top} />
        <Rig bounds={bounds} focus={focus} />
      </Canvas>

      <div className="viewer-controls">
        <label><input type="checkbox" checked={showCopper} onChange={(e) => setShowCopper(e.target.checked)} /> copper</label>
        <label><input type="checkbox" checked={showPlate} onChange={(e) => setShowPlate(e.target.checked)} /> plate</label>
        <label className="slice">
          slice
          <input type="range" min="0" max={top.toFixed(2)} step="0.05" value={sliceZ}
                 onChange={(e) => setSliceZ(Number(e.target.value))} />
          <span>{sliceZ > 0 ? `${sliceZ.toFixed(2)} mm` : 'off'}</span>
        </label>
        <span className="hint">drag to rotate · scroll to zoom</span>
      </div>
    </div>
  )
}
