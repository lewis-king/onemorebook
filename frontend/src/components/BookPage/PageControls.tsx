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
        <div class="page-controls-wrapper w-full">
            {/* Mobile: Compact inline controls */}
            <div class="flex md:hidden items-center justify-between w-full px-2 py-1">
                <A
                    href="/"
                    class="bg-white/90 text-kiddy-primary p-2 rounded-full shadow-md
                           hover:bg-white transition-all duration-200 flex-shrink-0"
                    title="Back to Stories"
                >
                    <span class="text-lg">🏠</span>
                </A>

                <div class="flex items-center gap-1">
                    <button
                        onClick={props.onPrevious}
                        disabled={props.currentPage === 0}
                        class="bg-kiddy-primary/90 text-white px-2 py-1 rounded-full
                               text-xs font-bold shadow-md transition-all duration-200
                               disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        ◀
                    </button>

                    <div class="font-comic text-sm text-kiddy-primary bg-white/90
                                rounded-full px-3 py-1 shadow-md whitespace-nowrap">
                        {props.currentPage + 1} / {props.totalPages}
                    </div>

                    <button
                        onClick={props.onNext}
                        disabled={props.currentPage === props.totalPages - 1}
                        class="bg-kiddy-primary/90 text-white px-2 py-1 rounded-full
                               text-xs font-bold shadow-md transition-all duration-200
                               disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        ▶
                    </button>
                </div>

                {/* Empty spacer for balance */}
                <div class="w-8"></div>
            </div>

            {/* Desktop: Full controls */}
            <div class="hidden md:flex flex-row justify-between items-center gap-4 my-6">
                <A
                    href="/"
                    class="bg-gradient-to-r from-kiddy-primary to-kiddy-secondary
                           text-white px-6 py-3 rounded-full font-bold shadow-lg
                           hover:shadow-xl transition-all duration-300 hover:-translate-y-1
                           active:translate-y-0 font-comic flex items-center gap-2"
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
                               hover:-translate-y-1 active:translate-y-0 font-comic"
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
                               hover:-translate-y-1 active:translate-y-0 font-comic"
                    >
                        Next 👉
                    </button>
                </div>

                <div class="w-[160px]"></div>
            </div>
        </div>
    );
};

export default PageControls;
