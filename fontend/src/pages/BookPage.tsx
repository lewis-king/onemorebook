import { createResource, createSignal, Show } from "solid-js";
import { useParams } from "@solidjs/router";
import { bookService } from "../services/api";
import { BookSpread } from "../components/BookPage/BookSpread";
import PageControls from "../components/BookPage/PageControls";
import StarRating from "../components/StarRating";

export default function BookPage() {
    const params = useParams();
    const [book, { refetch }] = createResource(() => params.id, bookService.getBook);
    const [currentPage, setCurrentPage] = createSignal(0);
    const [error, setError] = createSignal<string | null>(null);

    const pages = () => {
        if (!book()) return [];
        return ['cover', ...book()!.content.split('PAGE_BREAK'), 'rating'];
    };

    const handleUpvote = async (id: string, currentStars: number) => {
        try {
            await bookService.updateStars(id, currentStars);
            refetch();
        } catch (e) {
            console.error('Error updating stars:', e);
            setError(e instanceof Error ? e.message : 'Failed to update stars');
        }
    };

    let pageFlipRef: any;

    const handlePageChange = (newPage: number) => {
        if (!pageFlipRef) return;

        if (newPage > currentPage()) {
            pageFlipRef.flipNext();
        } else {
            pageFlipRef.flipPrev();
        }
        setCurrentPage(newPage);
    };

    const getCoverImage = () => {
        if (!book() || !book()?.coverImage) return undefined;
        return book()?.coverImage.url;
    };

    return (
        <div class="max-w-4xl mx-auto px-4">
            <Show when={error()}>
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                    {error()}
                </div>
            </Show>

            <Show
                when={!book.loading && book()}
                fallback={
                    <div class="text-center py-8">
                        Loading book...
                    </div>
                }
            >
                {(bookData) => (
                    <>
                        <div class="bg-[#f8f4e8] rounded-lg shadow-2xl p-8">
                            <BookSpread
                                pages={pages()}
                                coverImage={getCoverImage()}
                                onPageFlipInit={(pageFlip) => pageFlipRef = pageFlip}
                                onPageChange={(page) => setCurrentPage(page)}
                                bookId={bookData.id}
                                stars={bookData.stars}
                                onUpvote={handleUpvote}
                            />

                            <PageControls
                                currentPage={currentPage()}
                                totalPages={pages().length}
                                onPrevious={() => handlePageChange(Math.max(0, currentPage() - 1))}
                                onNext={() => handlePageChange(Math.min(pages().length - 1, currentPage() + 1))}
                            />
                        </div>
                    </>
                )}
            </Show>
        </div>
    );
}