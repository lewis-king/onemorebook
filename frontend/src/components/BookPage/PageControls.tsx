import { Component, Show } from "solid-js";
import { A } from "@solidjs/router";
import { TbArrowsMaximize, TbArrowsMinimize, TbChevronLeft, TbChevronRight } from "solid-icons/tb";

interface PageControlsProps {
    currentPage: number;
    totalPages: number;
    onPrevious: () => void;
    onNext: () => void;
    fullscreen: boolean;
    onToggleFullscreen: () => void;
}

const PageControls: Component<PageControlsProps> = (props) => {
    const progress = () =>
        props.totalPages > 0
            ? ((props.currentPage + 1) / props.totalPages) * 100
            : 0;

    return (
        <div class="page-controls-wrapper w-full select-none">
            <Show when={props.fullscreen}>
                {/* Floating pill — the only chrome in full screen */}
                <div class="absolute top-3 md:top-5 inset-x-0 z-20 flex justify-center pointer-events-none px-3">
                    <div class="pointer-events-auto flex items-center gap-2 md:gap-3 bg-white/85 backdrop-blur-md rounded-full p-1.5 pr-2.5 shadow-2xl border border-white/70">
                        <button
                            onClick={props.onToggleFullscreen}
                            title="Exit full screen"
                            class="w-9 h-9 rounded-full bg-kiddy-primary text-white flex items-center justify-center
                                   shadow-md hover:scale-105 active:scale-95 transition-transform flex-shrink-0"
                        >
                            <TbArrowsMinimize size={18} />
                        </button>

                        <div class="font-comic text-base md:text-lg text-kiddy-primary px-1 whitespace-nowrap">
                            {props.currentPage + 1} / {props.totalPages}
                        </div>

                        <button
                            onClick={props.onPrevious}
                            disabled={props.currentPage === 0}
                            title="Previous page"
                            class="w-9 h-9 rounded-full bg-kiddy-primary text-white flex items-center justify-center
                                   shadow-md hover:scale-105 active:scale-95 transition-transform flex-shrink-0
                                   disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            <TbChevronLeft size={20} />
                        </button>

                        <button
                            onClick={props.onNext}
                            disabled={props.currentPage === props.totalPages - 1}
                            title="Next page"
                            class="w-9 h-9 rounded-full bg-kiddy-primary text-white flex items-center justify-center
                                   shadow-md hover:scale-105 active:scale-95 transition-transform flex-shrink-0
                                   disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            <TbChevronRight size={20} />
                        </button>
                    </div>
                </div>
            </Show>

            <Show when={!props.fullscreen}>
                {/* Mobile: Compact inline controls */}
                <div class="flex md:hidden items-center justify-between w-full px-2 py-1">
                    <A
                        href="/"
                        class="bg-white/90 text-kiddy-primary w-10 h-10 rounded-full shadow-md
                               hover:bg-white transition-all duration-200 flex items-center justify-center flex-shrink-0
                               active:scale-90"
                        title="Back to Stories"
                    >
                        <span class="text-lg">🏠</span>
                    </A>

                    <div class="flex items-center gap-1.5">
                        <button
                            onClick={props.onPrevious}
                            disabled={props.currentPage === 0}
                            class="bg-kiddy-primary/90 text-white px-3.5 py-2.5 rounded-full
                                   text-sm font-bold shadow-md transition-all duration-200
                                   disabled:opacity-40 disabled:cursor-not-allowed active:scale-95"
                        >
                            ◀
                        </button>

                        <div class="font-comic text-sm text-kiddy-primary bg-white/90
                                    rounded-full px-3.5 py-2 shadow-md whitespace-nowrap">
                            {props.currentPage + 1} / {props.totalPages}
                        </div>

                        <button
                            onClick={props.onNext}
                            disabled={props.currentPage === props.totalPages - 1}
                            class="bg-kiddy-primary/90 text-white px-3.5 py-2.5 rounded-full
                                   text-sm font-bold shadow-md transition-all duration-200
                                   disabled:opacity-40 disabled:cursor-not-allowed active:scale-95"
                        >
                            ▶
                        </button>
                    </div>

                    <button
                        onClick={props.onToggleFullscreen}
                        title="Read in full screen"
                        class="bg-white/90 text-kiddy-primary w-10 h-10 rounded-full shadow-md
                               hover:bg-white transition-all duration-200 flex items-center justify-center flex-shrink-0
                               active:scale-90"
                    >
                        <TbArrowsMaximize size={20} />
                    </button>
                </div>

                {/* Desktop: Full controls */}
                <div class="hidden md:flex flex-row justify-between items-center gap-4 my-6">
                    <A
                        href="/"
                        class="bg-gradient-to-r from-kiddy-primary to-kiddy-secondary
                               text-white px-6 py-3 rounded-full font-bold shadow-lg
                               hover:shadow-xl transition-all duration-300 hover:-translate-y-1
                               active:translate-y-0 active:scale-95 font-comic flex items-center gap-2"
                    >
                        <span class="text-xl">🏠</span>
                        <span>Back to Stories</span>
                    </A>

                    <div class="flex items-center gap-4">
                        <button
                            onClick={props.onPrevious}
                            disabled={props.currentPage === 0}
                            class="bg-kiddy-primary text-white px-6 py-3 rounded-full
                                   font-bold shadow-lg hover:shadow-xl transition-all duration-300
                                   disabled:opacity-50 disabled:cursor-not-allowed
                                   hover:-translate-y-1 active:translate-y-0 active:scale-95 font-comic"
                        >
                            👈 Back
                        </button>

                        <div class="font-comic text-xl text-kiddy-primary bg-white/80
                                    backdrop-blur-sm rounded-full px-6 py-2 shadow-md whitespace-nowrap">
                            {props.currentPage + 1} / {props.totalPages}
                        </div>

                        <button
                            onClick={props.onNext}
                            disabled={props.currentPage === props.totalPages - 1}
                            class="bg-kiddy-primary text-white px-6 py-3 rounded-full
                                   font-bold shadow-lg hover:shadow-xl transition-all duration-300
                                   disabled:opacity-50 disabled:cursor-not-allowed
                                   hover:-translate-y-1 active:translate-y-0 active:scale-95 font-comic"
                        >
                            Next 👉
                        </button>
                    </div>

                    <div class="w-[160px] flex justify-end">
                        <button
                            onClick={props.onToggleFullscreen}
                            title="Read in full screen"
                            class="group bg-gradient-to-r from-kiddy-secondary to-kiddy-primary
                                   text-white px-5 py-3 rounded-full font-bold shadow-lg
                                   hover:shadow-xl transition-all duration-300 hover:-translate-y-1
                                   active:translate-y-0 active:scale-95 font-comic flex items-center gap-2 whitespace-nowrap"
                        >
                            <TbArrowsMaximize size={20} class="group-hover:animate-wiggle" />
                            <span class="hidden lg:inline">Big screen</span>
                        </button>
                    </div>
                </div>

                {/* Story progress: how far through the book are we? */}
                <div class="w-full max-w-md mx-auto mt-2 md:mt-3">
                    <div
                        class="h-2.5 rounded-full bg-white/70 shadow-inner overflow-hidden"
                        role="progressbar"
                        aria-valuemin="0"
                        aria-valuemax={props.totalPages}
                        aria-valuenow={props.currentPage + 1}
                        aria-label="Story progress"
                    >
                        <div
                            class="h-full rounded-full bg-gradient-to-r from-kiddy-primary to-kiddy-secondary transition-all duration-500"
                            style={{ width: `${progress()}%` }}
                        />
                    </div>
                </div>
            </Show>
        </div>
    );
};

export default PageControls;
