import { Component } from "solid-js";
import { A } from "@solidjs/router";

interface HeroButtonProps {
    href: string;
    children: any;
}

const HeroButton: Component<HeroButtonProps> = (props) => {
    return (
        <A
            href={props.href}
            class="inline-flex items-center justify-center gap-2
             bg-gradient-to-r from-kiddy-accent to-yellow-300
             text-kiddy-primary font-comic
             text-base sm:text-lg md:text-xl
             px-6 sm:px-8 md:px-10
             py-3 sm:py-4
             rounded-full
             transform hover:scale-105 active:scale-95
             transition-all duration-300
             shadow-lg hover:shadow-xl
             relative overflow-hidden
             group
             border-2 border-white/20"
        >
      <span class="relative z-10 flex items-center gap-2">
        {props.children}
      </span>

            {/* Shine effect */}
            <div class="absolute inset-0 opacity-0 group-hover:opacity-100
                  transition-opacity duration-300
                  bg-gradient-to-r from-transparent via-white/30 to-transparent
                  -skew-x-12 translate-x-[-150%] group-hover:translate-x-[150%]
                  transition-transform duration-700" />

            {/* Glow effect */}
            <div class="absolute inset-0 rounded-full opacity-0 group-hover:opacity-100
                  transition-opacity duration-300 blur-xl
                  bg-gradient-to-r from-yellow-200/50 to-yellow-400/50" />
        </A>
    );
};

export default HeroButton;