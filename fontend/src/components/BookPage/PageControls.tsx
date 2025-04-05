import { Component } from "solid-js";
import { A } from "@solidjs/router";

interface PageControlsProps {
    currentPage: number;
    totalPages: number;
    onPrevious: () => void;
    onNext: () => void;
}

const PageControls: Component<PageControlsProps> = (props) => {
    return (
        <div class="flex flex-col md:flex-row justify-between items-center gap-4 my-8">
            {/* Home button - moves to bottom on mobile */}
            <A
                href="/"
                class="bg-gradient-to-r from-kiddy-primary to-kiddy-secondary
               text-white px-4 md:px-6 py-2 md:py-3 rounded-full font-bold shadow-lg
               hover:shadow-xl transition-all duration-300 hover:-translate-y-1
               active:translate-y-0 font-comic flex items-center gap-2
               text-sm md:text-base w-full md:w-auto justify-center
               order-last md:order-first"
            >
                <span class="text-lg md:text-xl">🏠</span>
                <span>Back to Stories</span>
            </A>

            {/* Centered page controls */}
            <div class="flex items-center gap-2 md:gap-4 w-full md:w-auto justify-center order-first md:order-none">
                <button
                    onClick={props.onPrevious}
                    disabled={props.currentPage === 0}
                    class="bg-kiddy-primary text-white px-3 md:px-6 py-2 md:py-3 rounded-full
                 font-bold shadow-lg hover:shadow-xl transition-all duration-300
                 disabled:opacity-50 disabled:cursor-not-allowed
                 hover:-translate-y-1 active:translate-y-0
                 font-comic text-sm md:text-base whitespace-nowrap"
                >
                    👈 Back
                </button>

                <div class="font-comic text-base md:text-xl text-kiddy-primary bg-white/80
                    backdrop-blur-sm rounded-full px-3 md:px-6 py-2 shadow-md
                    whitespace-nowrap">
                    {props.currentPage + 1} / {props.totalPages}
                </div>

                <button
                    onClick={props.onNext}
                    disabled={props.currentPage === props.totalPages - 1}
                    class="bg-kiddy-primary text-white px-3 md:px-6 py-2 md:py-3 rounded-full
                 font-bold shadow-lg hover:shadow-xl transition-all duration-300
                 disabled:opacity-50 disabled:cursor-not-allowed
                 hover:-translate-y-1 active:translate-y-0
                 font-comic text-sm md:text-base whitespace-nowrap"
                >
                    Next 👉
                </button>
            </div>

            {/* Empty div for layout balance on desktop */}
            <div class="hidden md:block w-[160px] order-none"></div>
        </div>
    );
};

export default PageControls;