import React, { useState, useEffect, useRef } from 'react'
import { ArrowLeft, Camera, Save, User, X, ZoomIn, ZoomOut, Check } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Cropper from 'react-easy-crop'
import getCroppedImg from './utils/cropUtils'
import UserAvatar from './components/UserAvatar'
import { orionApi } from './utils/api';

// Constants
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];


export default function ProfilePage() {
    const { user, login, refreshUser } = useAuth() 
    const navigate = useNavigate()
    
    // -- Data State --
    const [displayName, setDisplayName] = useState('')
    const [statusMatch, setStatusMatch] = useState('Online') 
    const [description, setDescription] = useState('')
    const [avatarUrl, setAvatarUrl] = useState(null)
    
    // -- UI State --
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [error, setError] = useState(null)

    // -- Cropper State --
    const [showCropper, setShowCropper] = useState(false)
    const [cropImageSrc, setCropImageSrc] = useState(null)
    const [cropFileType, setCropFileType] = useState('image/jpeg')
    const [crop, setCrop] = useState({ x: 0, y: 0 })
    const [zoom, setZoom] = useState(1)
    const [croppedAreaPixels, setCroppedAreaPixels] = useState(null)
    const [isProcessingCrop, setIsProcessingCrop] = useState(false)

    // Refs
    const fileInputRef = useRef(null)

    // 1. Fetch Profile on Mount
    useEffect(() => {
        let isMounted = true;
        const fetchProfile = async () => {
            try {
                console.log(`Fetching profile...`);
                // orionApi handles path and headers
                const res = await orionApi.get('/api/profile')
                
                if (res.ok) {
                    const data = await res.json()
                    if (isMounted) {
                        setDisplayName(data.display_name || user?.username || '')
                        setStatusMatch(data.status_message || 'Online')
                        setDescription(data.description || 'Just a traveler in the Orion system.')
                        setAvatarUrl(data.avatar_url || null)
                    }
                } else {
                    console.error("Profile fetch failed:", res.status, res.statusText);
                }
            } catch (err) {
                console.error("Failed to fetch profile (Network Error?)", err)
            } finally {
                if (isMounted) setIsLoading(false)
            }
        }
        fetchProfile()

        return () => { isMounted = false }
    }, [user])

    // --- SAVE LOGIC ---
    const handleSave = async () => {
        setIsSaving(true)
        setError(null)
        try {
            const updates = {
                display_name: displayName,
                status_message: statusMatch,
                description: description
            }
            
            const res = await orionApi.post('/api/profile', updates);

            if (!res.ok) throw new Error("Failed to update profile")
            
            // Success
            alert("Profile saved successfully!")
            await refreshUser(); // Refresh user context after save

        } catch (err) {
            console.error(err)
            setError(err.message)
            alert("Error saving profile: " + err.message)
        } finally {
            setIsSaving(false)
        }
    }

    // --- UPLOAD LOGIC ---
    const uploadAvatarBlob = async (blob) => {
        try {
            console.log(`Uploading Blob: Size=${blob.size}, Type=${blob.type}`);

            const formData = new FormData()
            // Ext mapping
            let ext = 'jpg';
            if (blob.type === 'image/png') ext = 'png';
            if (blob.type === 'image/webp') ext = 'webp';
            if (blob.type === 'image/gif') ext = 'gif';

            formData.append('file', blob, `avatar.${ext}`) 

            console.log("Sending upload request...");
            
            // orionApi.post automatically handles FormData content-type logic
            const res = await orionApi.post('/api/profile/avatar', formData);

            console.log(`Upload Response Status: ${res.status}`);

            if (!res.ok) {
                const errorText = await res.text();
                // ...
                console.error("Upload Failed Server Response:", errorText);
                throw new Error(`Upload failed: ${res.status} ${res.statusText} - ${errorText}`)
            }

            const data = await res.json()
            console.log("Upload Successful:", data);
            
            setAvatarUrl(data.avatar_url)
            setShowCropper(false)
            await refreshUser(); // Refresh global user state
            // alert("Avatar updated!"); // Optional

        } catch (e) {
            console.error("Upload Error:", e)
            alert(`Failed to save avatar image: ${e.message}`)
        }
    }

    // --- AVATAR LOGIC ---
    const onFileSelect = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            const file = e.target.files[0]
            
            // Validation
            if (!ALLOWED_TYPES.includes(file.type)) {
                alert("Only JPEG, PNG, WEBP, and GIF are allowed.")
                return
            }
            if (file.size > MAX_FILE_SIZE) {
                alert("File size must be less than 5MB.")
                return
            }

            // GIF SPECIAL CASE: Skip Cropper to preserve animation
            if (file.type === 'image/gif') {
                if(window.confirm("Upload GIF directly? (Cropping disabled for animations)")) {
                    uploadAvatarBlob(file);
                }
                e.target.value = null;
                return;
            }

            // Store type for later
            setCropFileType(file.type)

            // Read file for Cropper
            const reader = new FileReader()
            reader.addEventListener('load', () => {
                setCropImageSrc(reader.result)
                setShowCropper(true)
                setZoom(1)
                setCrop({ x: 0, y: 0 })
            })
            reader.readAsDataURL(file)
            
            // Clear input so same file can be selected again if needed
            e.target.value = null
        }
    }

    const onCropComplete = (croppedArea, croppedAreaPixels) => {
        setCroppedAreaPixels(croppedAreaPixels)
    }

    const handleSaveCrop = async () => {
        setIsProcessingCrop(true)
        try {
            console.log("Starting crop processing...");
            
            // 1. Generate Cropped Blob
            let outputType = cropFileType;
            // NOTE: cropFileType will NEVER be gif here due to early exit above
            
            const croppedBlob = await getCroppedImg(cropImageSrc, croppedAreaPixels, 0, {horizontal:false, vertical:false}, outputType)
            
            // 2. Upload
            await uploadAvatarBlob(croppedBlob)

        } catch (e) {
            console.error("HandleSaveCrop Error:", e)
            alert(`Failed to save avatar image: ${e.message}`)
        } finally {
            setIsProcessingCrop(false)
        }
    }

    return (
        <div style={{
            flex: 1, 
            display: 'flex', 
            flexDirection: 'column', 
            padding: '2rem',
            maxWidth: '800px',
            margin: '0 auto',
            width: '100%',
            color: '#e4e4e7',
            fontFamily: 'Inter, sans-serif'
        }}>
            
            {/* Cropper Modal */}
            {showCropper && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 100,
                    background: 'rgba(0,0,0,0.85)',
                    display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center',
                    padding: '2rem'
                }}>
                    <div className="glass-panel" style={{
                        width: '100%', maxWidth: '500px', height: '80vh',
                        display: 'flex', flexDirection: 'column',
                        background: '#18181b', borderRadius: '16px', overflow: 'hidden'
                    }}>
                        {/* Header */}
                        <div style={{
                            padding: '1rem', borderBottom: '1px solid rgba(255,255,255,0.1)',
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                        }}>
                            <h3 style={{fontWeight: 600}}>Adjust Profile Picture</h3>
                            <button onClick={() => setShowCropper(false)} style={{background: 'transparent', border:'none', color:'#a1a1aa', cursor:'pointer'}}>
                                <X size={20} />
                            </button>
                        </div>

                        {/* Cropper Area */}
                        <div style={{flex: 1, position: 'relative', background: '#000'}}>
                            <Cropper
                                image={cropImageSrc}
                                crop={crop}
                                zoom={zoom}
                                aspect={1} // Force Square
                                onCropChange={setCrop}
                                onCropComplete={onCropComplete}
                                onZoomChange={setZoom}
                                cropShape="round" // Visual guide only, output is rect
                                showGrid={false}
                            />
                        </div>

                        {/* Controls */}
                        <div style={{padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                            <div style={{display: 'flex', alignItems: 'center', gap: '1rem', color: '#a1a1aa'}}>
                                <ZoomOut size={16} />
                                <input 
                                    type="range" 
                                    min={1} max={3} step={0.1}
                                    value={zoom}
                                    onChange={(e) => setZoom(e.target.value)}
                                    style={{flex: 1, accentColor: '#6366f1'}}
                                />
                                <ZoomIn size={16} />
                            </div>
                            
                            <button 
                                onClick={handleSaveCrop}
                                disabled={isProcessingCrop}
                                style={{
                                    width: '100%', padding: '0.8rem',
                                    background: '#6366f1', color: 'white',
                                    border: 'none', borderRadius: '8px',
                                    fontWeight: 600, cursor: 'pointer',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                                    opacity: isProcessingCrop ? 0.7 : 1
                                }}
                            >
                                {isProcessingCrop ? 'Processing...' : <><Check size={18} /> Apply</>}
                            </button>
                        </div>
                    </div>
                </div>
            )}


            {/* Main Header */}
            <div style={{marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '1rem'}}>
                <button onClick={() => navigate('/')} style={{
                    background: 'transparent', border: 'none', color: '#a1a1aa', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem'
                }}>
                    <ArrowLeft size={18} />
                    Back to Chat
                </button>
                <h1 style={{fontSize: '1.5rem', fontWeight: 'bold', marginLeft: 'auto'}}>Edit Profile</h1>
            </div>

            {/* Profile Content */}
            <div className="glass-panel" style={{padding: '2rem', borderRadius: '16px', background: 'rgba(255,255,255,0.03)'}}>
                
                {isLoading ? (
                    <div style={{textAlign: 'center', padding: '4rem', color: '#a1a1aa'}}>Loading Profile...</div>
                ) : (
                <>
                    {/* Avatar Section */}
                    <div style={{display: 'flex', gap: '2rem', alignItems: 'center', marginBottom: '2rem'}}>
                        <input 
                            type="file" 
                            ref={fileInputRef} 
                            style={{display:'none'}} 
                            accept={ALLOWED_TYPES.join(',')}
                            onChange={onFileSelect}
                        />
                        


                        <div style={{position: 'relative'}}>
                            <UserAvatar
                                avatarUrl={avatarUrl}
                                size={100}
                                style={{border: '2px solid rgba(255,255,255,0.1)'}}
                            />
                            
                            <button 
                                onClick={() => fileInputRef.current?.click()}
                                style={{
                                    position: 'absolute', bottom: 0, right: 0,
                                    background: '#6366f1', border: 'none', borderRadius: '50%',
                                    width: '32px', height: '32px',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    cursor: 'pointer', boxShadow: '0 4px 6px rgba(0,0,0,0.3)',
                                    zIndex: 10
                                }}
                                title="Change Avatar"
                            >
                                <Camera size={16} color="white" />
                            </button>
                        </div>
                        
                        <div style={{flex: 1}}>
                            <h2 style={{fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.25rem'}}>{displayName}</h2>
                            <div style={{color: '#a1a1aa', fontSize: '0.9rem'}}>User ID: {user?.user_id || 'Unknown'}</div>
                        </div>
                    </div>

                    {/* Form Fields */}
                    <div style={{display: 'flex', flexDirection: 'column', gap: '1.5rem'}}>
                        
                        {/* Username (Immutable) */}
                        <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                            <label style={{fontSize: '0.9rem', color: '#a1a1aa'}}>Username (Unique ID)</label>
                            <input 
                                type="text" 
                                value={user?.username || ''}
                                disabled
                                style={{
                                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.05)',
                                    padding: '0.75rem', borderRadius: '8px', color: '#71717a',
                                    outline: 'none', cursor: 'not-allowed'
                                }}
                            />
                        </div>

                        {/* Display Name */}
                        <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                            <label style={{fontSize: '0.9rem', color: '#a1a1aa'}}>Display Name</label>
                            <input 
                                type="text" 
                                value={displayName}
                                onChange={(e) => setDisplayName(e.target.value)}
                                placeholder="How others see you"
                                style={{
                                    background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)',
                                    padding: '0.75rem', borderRadius: '8px', color: 'white',
                                    outline: 'none'
                                }}
                            />
                        </div>

                        {/* Status */}
                        <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                            <label style={{fontSize: '0.9rem', color: '#a1a1aa'}}>Status Message</label>
                            <input 
                                type="text" 
                                value={statusMatch}
                                onChange={(e) => setStatusMatch(e.target.value)}
                                style={{
                                    background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)',
                                    padding: '0.75rem', borderRadius: '8px', color: 'white',
                                    outline: 'none'
                                }}
                            />
                        </div>

                         {/* Description */}
                         <div style={{display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
                            <label style={{fontSize: '0.9rem', color: '#a1a1aa'}}>About Me</label>
                            <textarea 
                                rows={4}
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                style={{
                                    background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)',
                                    padding: '0.75rem', borderRadius: '8px', color: 'white',
                                    outline: 'none', resize: 'none',
                                    fontFamily: 'inherit'
                                }}
                            />
                        </div>

                    </div>

                    {/* Action Bar */}
                    <div style={{marginTop: '2rem', display: 'flex', justifyContent: 'flex-end'}}>
                        <button 
                            onClick={handleSave}
                            disabled={isSaving}
                            style={{
                                background: '#6366f1', color: 'white',
                                border: 'none', padding: '0.75rem 1.5rem', borderRadius: '8px',
                                fontWeight: 600, cursor: isSaving ? 'wait' : 'pointer',
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                opacity: isSaving ? 0.7 : 1
                            }}
                        >
                            <Save size={18} />
                            {isSaving ? 'Saving...' : 'Save Changes'}
                        </button>
                    </div>
                </>
                )}
            </div>
        </div>
    )
}
