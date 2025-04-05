import { Component } from "solid-js";
import FloatingEmoji from "./FloatingEmoji";
import HeroButton from "./HeroButton";

const WelcomeHero: Component = () => {
    return (
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-kiddy-primary via-[#FF8E8E] to-kiddy-secondary p-4 md:p-8 lg:p-12">
            <div class="relative z-10 max-w-3xl mx-auto text-center py-8 md:py-12">
                <h1 class="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-comic text-white mb-4 md:mb-6 leading-tight">
                    Welcome to Your Story Adventure! ✨
                </h1>

                <p class="text-sm sm:text-base md:text-lg text-white/90 font-rounded max-w-2xl mx-auto mb-6 md:mb-8 leading-relaxed px-4">
                    Turn that familiar bedtime moment into endless adventures of your own creation!
                    Craft tales where dragons soar through starlit skies, brave teddy bears explore secret treasure caves, or pirate cats sail across bubble-filled oceans. Every story you imagine becomes the next chapter in your collection.
                </p>

                <HeroButton href="/create">
                    Create Your Own Story!
                    <span class="text-2xl">🌟</span>
                </HeroButton>
            </div>

            {/* Decorative elements with improved responsive positioning */}
            <div class="absolute inset-0 overflow-hidden pointer-events-none">
                <FloatingEmoji emoji="🐉" size="4xl" class="top-4 right-[5%] md:right-[10%]" />
                <FloatingEmoji emoji="✨" size="2xl" class="top-1/4 right-[15%] md:right-[20%]" delay="-2s" />
                <FloatingEmoji emoji="🌈" size="3xl" class="bottom-4 right-[8%] md:right-[15%]" delay="-1s" />
                <FloatingEmoji emoji="🦄" size="3xl" class="bottom-8 right-[20%] md:right-[25%]" delay="-3s" />
                <FloatingEmoji emoji="💫" size="2xl" class="top-1/3 right-[25%] md:right-[30%]" delay="-2.5s" />
                <FloatingEmoji emoji="🌙" size="2xl" class="top-1/2 left-[8%] md:left-[15%]" delay="-1.5s" />
                <FloatingEmoji emoji="🎨" size="2xl" class="top-1/4 left-[15%] md:left-[20%]" delay="-3.5s" />
                <FloatingEmoji emoji="🪄" size="2xl" class="bottom-1/3 left-[10%] md:left-[18%]" delay="-2.8s" />
            </div>

            {/* Enhanced gradient overlay */}
            <div class="absolute inset-0 bg-gradient-to-t from-black/10 to-transparent opacity-50" />
        </div>
    );
};

export default WelcomeHero;