import { Component } from "solid-js";

interface FloatingEmojiProps {
    emoji: string;
    size: string;
    delay?: string;
    class?: string;
}

const FloatingEmoji: Component<FloatingEmojiProps> = (props) => {
    return (
        <div
            class={`absolute animate-float ${props.class || ''} select-none opacity-75 hover:opacity-100 transition-opacity duration-300`}
            style={{
                "animation-delay": props.delay,
                "font-size": getSizeInRem(props.size),
                "filter": "drop-shadow(0 2px 4px rgba(0,0,0,0.1))",
                "transform-style": "preserve-3d",
                "backface-visibility": "hidden",
                "will-change": "transform",
                "text-rendering": "optimizeLegibility",
                "-webkit-font-smoothing": "antialiased",
                "-moz-osx-font-smoothing": "grayscale"
            }}
            aria-hidden="true"
        >
            {props.emoji}
        </div>
    );
};

function getSizeInRem(size: string): string {
    const sizes = {
        'sm': '1rem',
        'base': '1.25rem',
        'lg': '1.5rem',
        'xl': '1.75rem',
        '2xl': '2rem',
        '3xl': '2.5rem',
        '4xl': '3rem'
    };
    return sizes[size as keyof typeof sizes] || '1.5rem';
}

export default FloatingEmoji;