document.addEventListener('DOMContentLoaded', function () {
    const dataElement = document.getElementById('chart-data');
    if (!dataElement) return;

    let chartData;
    try {
        chartData = JSON.parse(dataElement.textContent);
    } catch (e) {
        console.error('Failed to parse chart data JSON', e);
        return;
    }

    // Helper for Indian Currency formatting
    function formatINR(val) {
        if (val === undefined || val === null) return '₹0';
        const s = Math.abs(val).toString();
        let formatted = s;
        if (s.length > 3) {
            const last3 = s.substring(s.length - 3);
            let rest = s.substring(0, s.length - 3);
            const groups = [];
            while (rest.length > 2) {
                groups.push(rest.substring(rest.length - 2));
                rest = rest.substring(0, rest.length - 2);
            }
            if (rest.length > 0) groups.push(rest);
            formatted = groups.reverse().join(',') + ',' + last3;
        }
        return (val < 0 ? '-₹' : '₹') + formatted;
    }

    const modernPalette = [
        '#4f46e5', // Indigo
        '#06b6d4', // Cyan
        '#10b981', // Emerald
        '#f59e0b', // Amber
        '#ef4444', // Red
        '#8b5cf6', // Violet
        '#ec4899', // Pink
        '#64748b'  // Slate
    ];

    // 1. Category Breakdown Doughnut Chart (FR-CHT-01)
    const catCanvas = document.getElementById('categoryChart');
    if (catCanvas && chartData.hasMonthExpenses && chartData.catLabels.length > 0) {
        const catTotal = chartData.catValues.reduce((a, b) => a + b, 0);

        new Chart(catCanvas, {
            type: 'doughnut',
            data: {
                labels: chartData.catLabels,
                datasets: [{
                    data: chartData.catValues,
                    backgroundColor: modernPalette.slice(0, chartData.catLabels.length),
                    borderWidth: 2,
                    borderColor: '#ffffff',
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            boxWidth: 12,
                            padding: 12,
                            font: { family: "'Plus Jakarta Sans', sans-serif", size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const val = context.raw || 0;
                                const pct = catTotal > 0 ? ((val / catTotal) * 100).toFixed(1) : 0;
                                return ` ${context.label}: ${formatINR(val)} (${pct}%)`;
                            }
                        }
                    }
                },
                cutout: '68%'
            }
        });
    }

    // 2. 6-Month Spending Trend Bar Chart (FR-CHT-02)
    const monthCanvas = document.getElementById('monthTrendChart');
    if (monthCanvas && chartData.monthChartLabels) {
        new Chart(monthCanvas, {
            type: 'bar',
            data: {
                labels: chartData.monthChartLabels,
                datasets: [{
                    label: 'Total Spend',
                    data: chartData.monthChartValues,
                    backgroundColor: '#4f46e5',
                    borderRadius: 8,
                    borderSkipped: false,
                    maxBarThickness: 38
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return ` Spend: ${formatINR(context.raw)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: '#f1f5f9' },
                        ticks: {
                            font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                            callback: function (val) {
                                return formatINR(val);
                            }
                        }
                    }
                }
            }
        });
    }

    // 3. Payment Mode Doughnut Chart (FR-PAY)
    const payCanvas = document.getElementById('paymentModeChart');
    if (payCanvas && chartData.hasMonthExpenses && chartData.payLabels) {
        const payTotal = chartData.payValues.reduce((a, b) => a + b, 0);

        new Chart(payCanvas, {
            type: 'doughnut',
            data: {
                labels: chartData.payLabels,
                datasets: [{
                    data: chartData.payValues,
                    backgroundColor: ['#10b981', '#3b82f6', '#06b6d4', '#f59e0b'],
                    borderWidth: 2,
                    borderColor: '#ffffff',
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            boxWidth: 10,
                            padding: 10,
                            font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const val = context.raw || 0;
                                const pct = payTotal > 0 ? ((val / payTotal) * 100).toFixed(1) : 0;
                                return ` ${context.label}: ${formatINR(val)} (${pct}%)`;
                            }
                        }
                    }
                },
                cutout: '65%'
            }
        });
    }
});
