import React from 'react';
import { User } from 'lucide-react';

/**
 * A smart component that renders either an image or a video loop based on the file extension.
 * Used for User Avatars to support efficient WebM formats.
 */
const UserAvatar = ({ avatarUrl, size = 32, alt = "User Avatar", style = {} }) => {
    
    // Fallback if no URL
    if (!avatarUrl) {
        return (
            <div style={{
                width: size, height: size, borderRadius: '50%', background: '#333',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                overflow: 'hidden', ...style
            }}>
                <User size={size * 0.5} color="#a1a1aa" />
            </div>
        );
    }

    // Check if it's a video
    const isVideo = avatarUrl.endsWith('.webm') || avatarUrl.endsWith('.mp4');

    const commonStyle = {
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        borderRadius: '50%'
    };

    const containerStyle = {
        width: size,
        height: size,
        borderRadius: '50%', // Ensure container is also round
        overflow: 'hidden',
        background: '#27272a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...style
    };

    return (
        <div style={containerStyle}>
            {isVideo ? (
                <video 
                    src={avatarUrl}
                    autoPlay 
                    loop 
                    muted 
                    playsInline 
                    style={commonStyle}
                    // Prevent download controls
                    controlsList="nodownload nofullscreen noremoteplayback"
                    disablePictureInPicture
                />
            ) : (
                <img 
                    src={avatarUrl} 
                    alt={alt} 
                    style={commonStyle} 
                />
            )}
        </div>
    );
};

export default UserAvatar;
