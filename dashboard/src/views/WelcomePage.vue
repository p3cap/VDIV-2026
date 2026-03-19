<script setup>
import { translateKey as t } from "@/data/translate.js";
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { animate, createTimeline } from 'animejs'
import { Users, Settings, File } from 'lucide-vue-next'

function animateAsync(target, params) {
	return new Promise((resolve) => {
		animate(target, { ...params, onComplete: resolve })
	})
}

const cards = [
	{
		id: 'about',
		icon: Users,
		color: 'cyan',
		label: 'card_about_label',
		title: 'card_about_title',
		blurb: 'card_about_blurb',
		stats: [
			{ label: 'card_about_stat_members', value: '3' },
			{ label: 'card_about_stat_project', value: '2026' },
		],
		members: [
			{
				name: 'member_torontali_name',
				role: 'member_torontali_role',
				avatar: 'TA',
				bio: 'member_torontali_bio',
				refUrl: 'https://github.com/torontali',
				refLabel: 'modal_references',
			},
			{
				name: 'member_kovacs_name',
				role: 'member_kovacs_role',
				avatar: 'KD',
				bio: 'member_kovacs_bio',
				refUrl: 'https://github.com/kovacsdavid0',
				refLabel: 'modal_references',
			},
			{
				name: 'member_dobosi_name',
				role: 'member_dobosi_role',
				avatar: 'DP',
				bio: 'member_dobosi_bio',
				refUrl: 'https://github.com/p3cap',
				refLabel: 'modal_references',
			},
		],
		sections: [
			{ title: 'section_team_intro_title', text: 'section_team_intro_text' },
			{ title: 'section_motivation_title', text: 'section_motivation_text' },
		],
	},
	{
		id: 'how',
		icon: Settings,
		color: 'orange',
		label: 'card_operation_label',
		title: 'card_operation_title',
		blurb: 'card_operation_blurb',
		stats: [
			{ label: 'card_operation_stat_stack', value: 'Vue 3, Node.js, websocket server' },
			{ label: 'card_operation_stat_render', value: 'Machine Learning, C++ pathfinding' },
		],
		sections: [
			{ title: 'card_operation_section_architecture_title', text: 'card_operation_section_architecture_text' },
			{ title: 'card_operation_section_technologies_title', text: 'card_operation_section_technologies_text' },
		],
	},
	{
		id: 'docs',
		icon: File,
		color: 'green',
		label: 'card_docs_label',
		title: 'card_docs_title',
		blurb: 'card_docs_blurb',
		sections: [
			{
				title: 'card_docs_section_title',
				text: 'card_docs_section_text',
				route: '/documentation',
			},
		],
	},
]

const accentMap = {
	cyan: 'var(--accent)',
	orange: 'var(--orange)',
	green: 'var(--clr-ok)',
}

// ── State ────────────────────────────────────────────────
const activeCard = ref(null)
const isAnimating = ref(false)

// ── Template refs ────────────────────────────────────────
const eyebrow = ref(null)
const title = ref(null)
const sub = ref(null)
const cardsGrid = ref(null)
const backdrop = ref(null)
const modal = ref(null)

// ── Escape key ───────────────────────────────────────────
function onKeydown(e) {
	if (e.key === 'Escape') closeModal()
}

// ── Mount ────────────────────────────────────────────────
onMounted(() => {
	backdrop.value.style.visibility = 'hidden'
	backdrop.value.style.opacity = '0'
	backdrop.value.style.pointerEvents = 'none'
	modal.value.style.opacity = '0'

	document.addEventListener('keydown', onKeydown)

	const cardEls = Array.from(cardsGrid.value?.querySelectorAll('.wcard') ?? [])
	const tl = createTimeline({ defaults: { ease: 'outExpo' } })

	tl.add(eyebrow.value, { opacity: [0, 1], translateY: [10, 0], duration: 600 })
		.add(title.value, { opacity: [0, 1], translateY: [24, 0], duration: 700 }, '-=400')
		.add(sub.value, { opacity: [0, 1], translateY: [14, 0], duration: 600 }, '-=480')

	cardEls.forEach((el, i) => {
		tl.add(el, {
			opacity: [0, 1],
			translateY: [32, 0],
			scale: [0.93, 1],
			duration: 550,
		}, `-=${i === 0 ? 280 : 460}`)
	})
})

onUnmounted(() => {
	document.removeEventListener('keydown', onKeydown)
})

// ── Open modal ───────────────────────────────────────────
async function openModal(card) {
	if (activeCard.value || isAnimating.value) return

	isAnimating.value = true
	activeCard.value = card

	await nextTick()

	modal.value.style.setProperty('--modal-accent', accentMap[card.color])

	const items = Array.from(
		modal.value.querySelectorAll('.wmodal__stat, .wmodal__member-card, .wmodal__section'),
	)
	items.forEach((el) => {
		el.style.opacity = '0'
		el.style.transform = 'translateY(10px)'
	})

	backdrop.value.style.visibility = 'visible'
	backdrop.value.style.opacity = '0'
	backdrop.value.style.pointerEvents = 'auto'
	modal.value.style.opacity = '0'
	modal.value.style.transform = 'translateY(36px) scale(0.95)'

	animate(backdrop.value, { opacity: [0, 1], duration: 280, ease: 'outQuad' })

	await animateAsync(modal.value, {
		translateY: [36, 0],
		scale: [0.95, 1],
		opacity: [0, 1],
		duration: 420,
		ease: 'outBack',
	})

	items.forEach((el, i) => {
		animate(el, {
			opacity: [0, 1],
			translateY: [10, 0],
			duration: 300,
			delay: i * 70,
			ease: 'outCubic',
		})
	})

	isAnimating.value = false
}

// ── Close modal ──────────────────────────────────────────
async function closeModal() {
	if (!activeCard.value || isAnimating.value) return

	isAnimating.value = true

	animate(backdrop.value, { opacity: [1, 0], duration: 260, ease: 'inCubic' })

	await animateAsync(modal.value, {
		translateY: [0, 28],
		scale: [1, 0.95],
		opacity: [1, 0],
		duration: 260,
		ease: 'inCubic',
	})

	backdrop.value.style.visibility = 'hidden'
	backdrop.value.style.pointerEvents = 'none'
	activeCard.value = null
	isAnimating.value = false
}
</script>

<template>
	<div class="welcome">
		<!-- ── Hero ─────────────────────────────── -->
		<div class="welcome-hero">
			<span ref="eyebrow" class="welcome-eyebrow">{{ t("welcome_eyebrow") }}</span>
			<h1 ref="title" class="welcome-title">{{ t("nav_welcome") }}</h1>
			<p ref="sub" class="welcome-sub">
				{{ t("welcome_sub") }}
				<strong style="color: var(--accent)">huh?!</strong>
				{{ t("team") }}
			</p>
		</div>

		<!-- ── Cards grid ────────────────────────── -->
		<div class="welcome-cards" ref="cardsGrid">
			<div
				v-for="card in cards"
				:key="card.id"
				class="wcard"
				:class="`wcard--${card.color}`"
				@click.stop="openModal(card)"
			>
				<div class="wcard__icon">
					<component :is="card.icon" />
				</div>
				<div class="wcard__label">{{ t(card.label) }}</div>
				<h3 class="wcard__title">{{ t(card.title) }}</h3>
				<p class="wcard__blurb">{{ t(card.blurb) }}</p>
				<div class="wcard__arrow">
					<svg
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
						stroke-linecap="round"
						stroke-linejoin="round"
						width="14"
						height="14"
					>
						<path d="M5 12h14M12 5l7 7-7 7" />
					</svg>
					{{ t("welcome_view") }}
				</div>
			</div>
		</div>

		<!-- ── Modal backdrop ────────────────────── -->
		<Teleport to="body">
			<div ref="backdrop" class="wmodal-backdrop" @click.self="closeModal">
				<div
					ref="modal"
					class="wmodal"
					role="dialog"
					aria-modal="true"
					:aria-label="t(activeCard?.title)"
				>
					<!-- Header -->
					<div class="wmodal__head">
						<div class="wmodal__head-left">
							<div class="wmodal__icon">
								<component :is="activeCard?.icon" />
							</div>
							<div class="wmodal__titles">
								<div class="wmodal__label">{{ t(activeCard?.label) }}</div>
								<h2 class="wmodal__title">{{ t(activeCard?.title) }}</h2>
							</div>
						</div>
						<button class="wmodal__close" @click.stop="closeModal" :aria-label="t('modal_close')">
							<svg
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								width="16"
								height="16"
							>
								<path d="M18 6 6 18M6 6l12 12" />
							</svg>
						</button>
					</div>

					<!-- Body -->
					<div class="wmodal__body">
						<!-- Stat strip -->
						<div class="wmodal__stats" v-if="activeCard?.stats?.length">
							<div class="wmodal__stat" v-for="s in activeCard.stats" :key="s.label">
								<div class="wmodal__stat-label">{{ t(s.label) }}</div>
								<div class="wmodal__stat-value" v-if="!s.link">{{ s.value }}</div>
								<div class="wmodal__stat-link" v-else>
									<a :href="s.link" target="_blank" rel="noopener noreferrer">{{ t('modal_open') }}</a>
								</div>
							</div>
						</div>

						<!-- Member cards -->
						<div class="wmodal__members" v-if="activeCard?.members?.length">
							<div
								class="wmodal__member-card"
								v-for="m in activeCard.members"
								:key="m.name"
							>
								<div class="wmodal__member-avatar">{{ m.avatar }}</div>
								<div class="wmodal__member-info">
									<div class="wmodal__member-top">
										<span class="wmodal__member-name">{{ t(m.name) }}</span>
										<span class="wmodal__member-role">{{ t(m.role) }}</span>
									</div>
									<p class="wmodal__member-bio">{{ t(m.bio) }}</p>
									<a
										v-if="m.refUrl"
										:href="m.refUrl"
										target="_blank"
										rel="noopener noreferrer"
										class="wmodal__member-link"
									>
										<svg
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="1.8"
											stroke-linecap="round"
											stroke-linejoin="round"
											width="12"
											height="12"
										>
											<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
											<polyline points="15 3 21 3 21 9" />
											<line x1="10" y1="14" x2="21" y2="3" />
										</svg>
										{{ t(m.refLabel) }}
									</a>
								</div>
							</div>
						</div>

						<!-- Szöveges szekciók -->
						<div
							class="wmodal__section"
							v-for="section in activeCard?.sections"
							:key="section.title"
						>
							<div class="wmodal__section-title">{{ t(section.title) }}</div>
							<p class="wmodal__section-text">{{ t(section.text) }}</p>
							<!-- Internal Vue route -->
							<RouterLink
								v-if="section.route"
								:to="section.route"
								class="wmodal__section-link"
							>
								<svg
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.8"
									stroke-linecap="round"
									stroke-linejoin="round"
									width="12"
									height="12"
								>
									<path d="M5 12h14M12 5l7 7-7 7" />
								</svg>
								{{ t("modal_open") }}
							</RouterLink>
							<!-- External URL -->
							<a
								v-else-if="section.link"
								:href="section.link"
								target="_blank"
								rel="noopener noreferrer"
								class="wmodal__section-link"
							>
								<svg
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.8"
									stroke-linecap="round"
									stroke-linejoin="round"
									width="12"
									height="12"
								>
									<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
									<polyline points="15 3 21 3 21 9" />
									<line x1="10" y1="14" x2="21" y2="3" />
								</svg>
								{{ t("modal_open") }}
							</a>
						</div>
					</div>

					<!-- Footer -->
					<div class="wmodal__foot">
						<button class="wmodal__btn wmodal__btn--primary" @click.stop="closeModal">
							{{ t("modal_close") }}
						</button>
					</div>
				</div>
			</div>
		</Teleport>
	</div>
</template>

<style src="../styles/welcome.css"></style>